"""Unit-Tests je Prüfschritt von ``scripts/verify_metadata_cutover.py`` (#1590).

Jeder Schritt wird einmal grün und einmal rot gefahren. Die Datenbank- und
Dateischritte werden über ihre Skriptfunktionen ersetzt — die echten
Vergleiche prüft ``tests/integration/test_verify_metadata_cutover.py``.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from scripts import verify_metadata_cutover as cutover

URL = 'postgresql+psycopg://u:geheim@host:5432/db'


def _config(**overrides: Any) -> SimpleNamespace:
    base = dict(
        DATABASE_URL=URL,
        METADATA_BACKEND='legacy',
        LLM_PROFILE_BACKEND='sqlite',
        PROJECT_BACKEND='file',
        SIMULATION_BACKEND='file',
        RUN_BACKEND='file',
        REPORT_BACKEND='file',
    )
    base.update(overrides)
    return SimpleNamespace(**base)


# -- flags -------------------------------------------------------------------


def test_flags_green_for_defaults_with_url():
    assert cutover.check_flags(_config()).status == cutover.OK


def test_flags_green_for_the_full_postgres_chain():
    config = _config(
        LLM_PROFILE_BACKEND='postgres',
        PROJECT_BACKEND='postgres',
        SIMULATION_BACKEND='postgres',
        RUN_BACKEND='postgres',
        REPORT_BACKEND='postgres',
    )
    assert cutover.check_flags(config).status == cutover.OK


@pytest.mark.parametrize(
    ('overrides', 'expected'),
    [
        ({'SIMULATION_BACKEND': 'postgres'}, 'AGORA_PROJECT_BACKEND=postgres'),
        ({'RUN_BACKEND': 'postgres'}, 'AGORA_SIMULATION_BACKEND=postgres'),
        ({'REPORT_BACKEND': 'postgres'}, 'AGORA_SIMULATION_BACKEND=postgres'),
        ({'RUN_BACKEND': 'postgress'}, "unknown value 'postgress'"),
        ({'DATABASE_URL': ''}, 'DATABASE_URL'),
    ],
)
def test_flags_red_for_broken_fk_order_or_missing_url(overrides, expected):
    result = cutover.check_flags(_config(**overrides))

    assert result.status == cutover.FAILED
    assert any(expected in line for line in result.details)


# -- alembic_head --------------------------------------------------------------


def test_alembic_head_green(monkeypatch):
    from app.infrastructure.postgres import schema_gate

    monkeypatch.setattr(schema_gate, 'verify_schema_at_head', lambda url: None)

    assert cutover.check_alembic_head(URL).status == cutover.OK


def test_alembic_head_red_names_revisions_not_the_url(monkeypatch):
    from app.infrastructure.postgres import schema_gate

    def drift(url):
        raise schema_gate.SchemaDriftError('Aktuelle Revision: aaa, erwartete Revision (Head): bbb.')

    monkeypatch.setattr(schema_gate, 'verify_schema_at_head', drift)
    result = cutover.check_alembic_head(URL)

    assert result.status == cutover.FAILED
    assert 'bbb' in result.details[0]
    assert 'geheim' not in cutover.render([result])


def test_alembic_head_unchecked_without_url():
    assert cutover.check_alembic_head('').status == cutover.UNCHECKED


# -- Datenvergleich je Domäne --------------------------------------------------


def _verify_result(checked: int, deviations: list[str], mismatched: set[str]) -> Any:
    return SimpleNamespace(
        checked=checked, deviations=deviations, verified=checked - len(mismatched)
    )


@pytest.mark.parametrize(
    ('name', 'module', 'check'),
    [
        ('simulations', 'migrate_simulations_to_postgres', cutover.check_simulations),
        ('runs', 'migrate_runs_to_postgres', cutover.check_runs),
        ('reports', 'migrate_reports_to_postgres', cutover.check_reports),
    ],
)
def test_verify_result_steps_green_and_red(monkeypatch, tmp_path, name, module, check):
    import importlib

    skript = importlib.import_module(f'scripts.{module}')
    options = cutover.CutoverOptions(uploads_dir=tmp_path, simulations_dir=tmp_path / 'simulations')

    monkeypatch.setattr(skript, 'verify', lambda root: _verify_result(3, [], set()))
    green = check(options)
    assert (green.name, green.status, green.verified, green.checked) == (name, cutover.OK, 3, 3)

    monkeypatch.setattr(
        skript, 'verify', lambda root: _verify_result(3, ['x.status: Datei=a DB=b'], {'x'})
    )
    red = check(options)
    assert (red.status, red.verified, red.checked) == (cutover.FAILED, 2, 3)
    assert red.details == ['x.status: Datei=a DB=b']


def test_projects_green_and_red(monkeypatch, tmp_path):
    from scripts import migrate_projects_to_postgres as skript

    options = cutover.CutoverOptions(uploads_dir=tmp_path)
    monkeypatch.setattr(skript, 'read_file_projects', lambda root: [object(), object()])

    monkeypatch.setattr(skript, 'verify', lambda root: [])
    assert cutover.check_projects(options).status == cutover.OK

    monkeypatch.setattr(skript, 'verify', lambda root: ['proj_a.name: Datei=x DB=y'])
    red = cutover.check_projects(options)
    assert (red.status, red.verified, red.checked) == (cutover.FAILED, 1, 2)


def test_llm_profiles_green_without_database_file(tmp_path):
    options = cutover.CutoverOptions(llm_profiles_db=tmp_path / 'gibtesnicht.db')

    assert cutover.check_llm_profiles(options).status == cutover.OK


def test_llm_profiles_red(monkeypatch, tmp_path):
    from scripts import migrate_llm_profiles_to_postgres as skript

    db = tmp_path / 'llm_profiles.db'
    db.write_bytes(b'')
    options = cutover.CutoverOptions(llm_profiles_db=db, secrets_dir=tmp_path)
    monkeypatch.setattr(skript, 'read_sqlite_profiles', lambda path: [{}, {}])

    monkeypatch.setattr(skript, 'verify', lambda path, secrets: [])
    assert cutover.check_llm_profiles(options).status == cutover.OK

    monkeypatch.setattr(skript, 'verify', lambda path, secrets: ['abc: fehlt in PostgreSQL'])
    red = cutover.check_llm_profiles(options)
    assert (red.status, red.verified, red.checked) == (cutover.FAILED, 1, 2)


# -- baseline ------------------------------------------------------------------


def _manifest(tmp_path: Path, name: str, ids: list[str], *, unchecked: bool = False) -> Path:
    data = {
        'classes': [
            {
                'name': 'runs',
                'count': len(ids),
                'ids': ids,
                'records': {i: {'status': 'completed'} for i in ids},
                'unchecked': unchecked,
            }
        ],
        'artifacts': {},
        'artifacts_unchecked': False,
    }
    path = tmp_path / name
    path.write_text(json.dumps(data), encoding='utf-8')
    return path


def test_baseline_green(tmp_path):
    paths = [_manifest(tmp_path, 'a.json', ['r1']), _manifest(tmp_path, 'b.json', ['r1'])]
    assert cutover.check_baseline(paths).status == cutover.OK


def test_baseline_red_when_an_id_disappears(tmp_path):
    paths = [_manifest(tmp_path, 'a.json', ['r1', 'r2']), _manifest(tmp_path, 'b.json', ['r1'])]
    result = cutover.check_baseline(paths)

    assert result.status == cutover.FAILED
    assert any('verschwunden' in line for line in result.details)


def test_baseline_unchecked_without_manifests_or_with_unchecked_class(tmp_path):
    assert cutover.check_baseline(None).status == cutover.UNCHECKED
    paths = [
        _manifest(tmp_path, 'a.json', ['r1'], unchecked=True),
        _manifest(tmp_path, 'b.json', ['r1']),
    ]
    assert cutover.check_baseline(paths).status == cutover.UNCHECKED


# -- Ablauf und Exit-Code --------------------------------------------------------


def _patch_all_steps(monkeypatch, status_by_name: dict[str, str]) -> None:
    def fake(name):
        return lambda *args, **kwargs: cutover.StepResult(
            name=name, status=status_by_name.get(name, cutover.OK), checked=1, verified=1
        )

    for name in ('flags', 'alembic_head', 'llm_profiles', 'projects', 'simulations', 'runs', 'reports', 'baseline'):
        monkeypatch.setattr(cutover, f'check_{name}', fake(name))


def test_all_green_exits_zero_in_cutover_order(monkeypatch, tmp_path):
    _patch_all_steps(monkeypatch, {})
    results = cutover.run_checks(cutover.CutoverOptions(uploads_dir=tmp_path), _config())

    assert [r.name for r in results] == [
        'flags', 'alembic_head', 'llm_profiles', 'projects', 'simulations', 'runs', 'reports', 'baseline'
    ]
    assert cutover.exit_code(results) == 0
    out = cutover.render(results)
    assert 'Scanned:   8' in out and 'Failed:    0' in out and 'Verified:  8/8' in out


def test_one_failure_exits_one_and_unchecked_exits_two(monkeypatch, tmp_path):
    _patch_all_steps(monkeypatch, {'runs': cutover.FAILED, 'baseline': cutover.UNCHECKED})
    results = cutover.run_checks(cutover.CutoverOptions(uploads_dir=tmp_path), _config())
    assert cutover.exit_code(results) == 1

    _patch_all_steps(monkeypatch, {'baseline': cutover.UNCHECKED})
    results = cutover.run_checks(cutover.CutoverOptions(uploads_dir=tmp_path), _config())
    assert cutover.exit_code(results) == 2
    assert 'Skipped:   1' in cutover.render(results)


def test_a_raising_step_fails_alone_and_hides_the_message(monkeypatch, tmp_path):
    _patch_all_steps(monkeypatch, {})

    def boom(options):
        raise RuntimeError(f'connection to {URL} failed')

    monkeypatch.setattr(cutover, 'check_runs', boom)
    results = cutover.run_checks(cutover.CutoverOptions(uploads_dir=tmp_path), _config())

    runs = next(r for r in results if r.name == 'runs')
    assert runs.status == cutover.FAILED
    assert runs.details == ['Schritt abgebrochen: RuntimeError']
    assert 'geheim' not in cutover.render(results)
    assert [r.status for r in results if r.name != 'runs'] == [cutover.OK] * 7

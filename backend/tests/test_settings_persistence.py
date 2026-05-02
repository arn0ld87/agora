"""Tests für den Schreib-Pfad des SettingsService (Issue #133, SUB2).

Pinnt:
  1. Atomic-Write per ``tmp + os.replace`` — keine korrupte JSON nach
     simulierten Crashes, kein zurückgelassenes ``.tmp`` im Happy-Path.
  2. ``apply_payload`` mergt mit existierender File-Layer und ersetzt
     sie nicht.
  3. Override wird nach erfolgreichem Persist geräumt, sodass
     ``GET /api/settings`` ``source=file`` zeigt (nicht ``override``).
  4. ``remove_persisted`` löscht Keys aus File und Override.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from app.services.settings_layer import (
    SOURCE_DEFAULT,
    SOURCE_FILE,
    SOURCE_OVERRIDE,
    SettingsService,
)


@pytest.fixture
def service(tmp_path: Path, monkeypatch) -> SettingsService:
    # env clean halten, damit die Source-Auflösung deterministisch ist
    for var in ('LLM_MODEL_NAME', 'NEO4J_PASSWORD', 'REPORT_LANGUAGE',
                'AGORA_LOG_FORMAT', 'EMBEDDING_MODEL', 'VECTOR_DIM'):
        monkeypatch.delenv(var, raising=False)
    return SettingsService(instance_path=tmp_path / 'settings.json')


# ---------------------------------------------------------------------------
# Atomic-Write
# ---------------------------------------------------------------------------


def test_apply_payload_creates_instance_file(service):
    service.apply_payload({'LLM_MODEL_NAME': 'qwen2.5:14b'}, persist=True)
    assert service.instance_path.exists()
    data = json.loads(service.instance_path.read_text(encoding='utf-8'))
    assert data == {'LLM_MODEL_NAME': 'qwen2.5:14b'}


def test_apply_payload_merges_with_existing_file(service):
    service.instance_path.parent.mkdir(parents=True, exist_ok=True)
    service.instance_path.write_text(
        json.dumps({'REPORT_LANGUAGE': 'English', 'TIME_PROFILE': 'usa_default'}),
        encoding='utf-8',
    )
    service.apply_payload({'REPORT_LANGUAGE': 'German'}, persist=True)
    data = json.loads(service.instance_path.read_text(encoding='utf-8'))
    # ``TIME_PROFILE`` darf nicht verloren gehen, ``REPORT_LANGUAGE``
    # ist überschrieben.
    assert data == {'REPORT_LANGUAGE': 'German', 'TIME_PROFILE': 'usa_default'}


def test_apply_payload_no_tmp_left_behind_on_success(service):
    service.apply_payload({'LLM_MODEL_NAME': 'qwen2.5:14b'}, persist=True)
    leftovers = list(service.instance_path.parent.glob('*.tmp'))
    leftovers += list(service.instance_path.parent.glob('settings.*.json.tmp'))
    assert leftovers == []


def test_atomic_write_uses_replace_not_unlink(service, monkeypatch):
    """Wir wollen ``os.replace`` als finalen Schritt sehen — falls
    jemand auf ``os.rename``/``Path.write_text`` umstellt, fängt das
    diesen Test.
    """
    seen_calls: list[tuple[str, str]] = []
    real_replace = os.replace

    def tracking_replace(src, dst):
        seen_calls.append((str(src), str(dst)))
        return real_replace(src, dst)

    monkeypatch.setattr(
        'app.services.settings_layer.os.replace', tracking_replace
    )
    service.apply_payload({'LLM_MODEL_NAME': 'qwen2.5:14b'}, persist=True)
    assert len(seen_calls) == 1
    src, dst = seen_calls[0]
    assert dst == str(service.instance_path)
    assert src.endswith('.json.tmp')


def test_atomic_write_cleans_up_tmp_on_failure(service, monkeypatch):
    """Gemini-Finding (PR #155): wenn ``json.dump`` oder ``fsync``
    während des atomic Writes scheitert, soll keine ``settings.*.json.tmp``
    im ``instance/``-Verzeichnis verwaisen.
    """
    real_dump = json.dump

    def boom(*args, **kwargs):
        # Erst echten Inhalt schreiben (damit eine Tempdatei existiert),
        # dann Fehler werfen.
        real_dump({'partial': True}, args[1])
        raise RuntimeError('forced failure')

    monkeypatch.setattr('app.services.settings_layer.json.dump', boom)

    with pytest.raises(RuntimeError):
        service.apply_payload({'LLM_MODEL_NAME': 'qwen2.5:14b'}, persist=True)

    leftovers = list(service.instance_path.parent.glob('settings.*.json.tmp'))
    assert leftovers == [], (
        f'Tempdatei nicht aufgeräumt nach Fehler: {leftovers}'
    )
    # Ziel-Datei existiert nicht — wir hatten ja noch nichts erfolgreich
    # zu schreiben.
    assert not service.instance_path.exists()


def test_concurrent_writes_do_not_corrupt_file(service):
    """Smoke-Test für das Lock — zwei sequentielle, aber back-to-back
    apply_payload-Calls dürfen kein partielles JSON hinterlassen.
    """
    service.apply_payload({'REPORT_LANGUAGE': 'German'}, persist=True)
    service.apply_payload({'TIME_PROFILE': 'dach_default'}, persist=True)
    data = json.loads(service.instance_path.read_text(encoding='utf-8'))
    assert data == {'REPORT_LANGUAGE': 'German', 'TIME_PROFILE': 'dach_default'}


# ---------------------------------------------------------------------------
# Source-Resolver-Verhalten nach Persist
# ---------------------------------------------------------------------------


def test_persisted_field_shows_source_file_not_override(service):
    service.apply_payload({'LLM_MODEL_NAME': 'qwen2.5:14b'}, persist=True)
    state = service.get_field_state('LLM_MODEL_NAME')
    assert state['source'] == SOURCE_FILE
    assert state['value'] == 'qwen2.5:14b'


def test_apply_without_persist_keeps_override(service):
    service.apply_payload({'LLM_MODEL_NAME': 'qwen2.5:14b'}, persist=False)
    state = service.get_field_state('LLM_MODEL_NAME')
    assert state['source'] == SOURCE_OVERRIDE
    assert not service.instance_path.exists()


def test_apply_payload_returns_merged_file_layer(service):
    service.apply_payload({'REPORT_LANGUAGE': 'English'}, persist=True)
    merged = service.apply_payload({'TIME_PROFILE': 'dach_default'}, persist=True)
    assert merged == {'REPORT_LANGUAGE': 'English', 'TIME_PROFILE': 'dach_default'}


def test_apply_empty_payload_is_noop(service):
    service.apply_payload({}, persist=True)
    assert not service.instance_path.exists()


# ---------------------------------------------------------------------------
# remove_persisted (Reset auf Default)
# ---------------------------------------------------------------------------


def test_remove_persisted_drops_key_and_returns_to_default(service):
    service.apply_payload({'LLM_MODEL_NAME': 'qwen2.5:14b'}, persist=True)
    service.remove_persisted(['LLM_MODEL_NAME'])
    state = service.get_field_state('LLM_MODEL_NAME')
    assert state['source'] == SOURCE_DEFAULT


def test_remove_persisted_preserves_other_keys(service):
    service.apply_payload(
        {'LLM_MODEL_NAME': 'qwen2.5:14b', 'REPORT_LANGUAGE': 'English'},
        persist=True,
    )
    service.remove_persisted(['LLM_MODEL_NAME'])
    data = json.loads(service.instance_path.read_text(encoding='utf-8'))
    assert data == {'REPORT_LANGUAGE': 'English'}


def test_remove_persisted_for_missing_key_is_noop(service):
    service.apply_payload({'LLM_MODEL_NAME': 'a'}, persist=True)
    service.remove_persisted(['VECTOR_DIM'])  # nicht im File
    data = json.loads(service.instance_path.read_text(encoding='utf-8'))
    assert data == {'LLM_MODEL_NAME': 'a'}


# ---------------------------------------------------------------------------
# Secrets im File
# ---------------------------------------------------------------------------


def test_persisted_secret_does_not_leak_in_get(service):
    service.apply_payload({'NEO4J_PASSWORD': 'super-secret'}, persist=True)
    state = service.get_field_state('NEO4J_PASSWORD')
    # Auch nachdem wir das Secret persistiert haben, GET muss
    # weiter ``value: null`` und ``is_set: true`` liefern.
    assert state['value'] is None
    assert state['is_set'] is True
    assert state['source'] == SOURCE_FILE


def test_persisted_secret_round_trip(service):
    """Service hat den Wert intern — er darf bei einer freundlichen
    API verfügbar sein, aber nie über das öffentliche GET. Der File-
    Inhalt enthält den Klartext (Issue-Akzeptanz: persistiere nach
    instance/settings.json), das ist eine bewusste Trade-Off.
    """
    service.apply_payload({'AGORA_AUTH_TOKEN': 'tok-xyz'}, persist=True)
    data = json.loads(service.instance_path.read_text(encoding='utf-8'))
    assert data['AGORA_AUTH_TOKEN'] == 'tok-xyz'

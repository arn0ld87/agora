"""Parity-Guard fuer das Image-Artefakt in `.github/workflows/docker-image.yml`.

Der Job `build-only` exportierte das Prod-Image als Tar und lud es
bedingungslos per `upload-artifact` hoch. Abgeholt wird dieses Artefakt von
genau einem Job — `prod-proxy-smoke` —, und dessen `if:`-Guard laesst nur
`workflow_dispatch`, Tags und Release-/RC-Branches durch. Auf einem
Pull-Request-Lauf wird er geskippt, `publish` haengt an ihm und wird
ebenfalls geskippt: Der Upload hatte dort schlicht keinen Konsumenten.

Folgenlos war das nicht. Das Prod-Image traegt die volle Backend-venv
inklusive der CUDA-Kette; der Tar liegt im Gigabyte-Bereich. Im Lauf
30825988931 (PR #1045) starb der Runner nach 1,64 GB hochgeladener Bytes
mit „The runner has received a shutdown signal", nachdem der Job zuvor
bereits 10 Minuten in Build, Trivy und SBOM verbracht hatte. Genau diese
Kombination aus Tar, Daemon-Layern und Cache-Export hatte in #994 schon
einmal ohne Fehlermeldung abgebrochen.

Der Fix gated den Upload auf `IMAGE_ARTIFACT_NEEDED` am Job-Kopf. Damit
existiert die Trigger-Bedingung an zwei Stellen — hier und im `if:` von
`prod-proxy-smoke`. Laufen sie auseinander, entsteht der teurere der beiden
Fehler lautlos: `prod-proxy-smoke` startet auf einem Release-Branch und
findet kein Artefakt, der Download bricht ab, und der Smoke-Gate vor dem
Registry-Push faellt aus. Dieser Test haelt beide Bedingungen zeichengleich.

Rohtext-Parser statt YAML-Bibliothek — dieselbe Begruendung wie in
`test_ci_gate_parity.py`: `pyyaml` ist im Repo keine deklarierte Dependency
und kaeme nur transitiv herein. Ein Test im verpflichtenden PR-Gate
(`uv run pytest tests/contracts/`) darf keine jederzeit lautlos entfernbare
Kopplung eingehen.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "docker-image.yml"

BUILD_JOB = "build-only"
SMOKE_JOB = "prod-proxy-smoke"
UPLOAD_STEP_NAME = "Image-Artefakt hochladen"
ENV_KEY = "IMAGE_ARTIFACT_NEEDED"
EXPECTED_STEP_GUARD = f"env.{ENV_KEY} == 'true'"


def _workflow_lines() -> list[str]:
    return WORKFLOW_PATH.read_text(encoding="utf-8").splitlines()


def _indent_of(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def _job_block(job_name: str) -> list[str]:
    """Sammelt die Rohtext-Zeilen eines Jobs (ohne dessen Kopfzeile).

    Der Block endet an der ersten nicht-leeren Zeile, deren Einrueckung
    kleiner oder gleich der Kopfzeile ist — also beim naechsten Job.
    """
    lines = _workflow_lines()
    for index, line in enumerate(lines):
        if line.strip() != f"{job_name}:":
            continue
        head_indent = _indent_of(line)
        block: list[str] = []
        for candidate in lines[index + 1 :]:
            if candidate.strip() and _indent_of(candidate) <= head_indent:
                break
            block.append(candidate)
        return block
    raise AssertionError(f"Job '{job_name}' nicht in {WORKFLOW_PATH.name} gefunden")


def _scalar_value(block: list[str], key: str) -> str:
    """Liest einen (auch gefalteten) Skalarwert `key:` aus einem Zeilenblock.

    Deckt sowohl `key: wert` als auch `key: >-` mit eingerueckten
    Folgezeilen ab. Rueckgabe ist der rohe, noch nicht normalisierte Wert.
    """
    for index, line in enumerate(block):
        stripped = line.strip()
        if not stripped.startswith(f"{key}:"):
            continue
        key_indent = _indent_of(line)
        inline = stripped[len(key) + 1 :].strip()
        if inline and inline not in (">-", ">", "|", "|-"):
            return inline
        folded: list[str] = []
        for candidate in block[index + 1 :]:
            if not candidate.strip():
                continue
            if _indent_of(candidate) <= key_indent:
                break
            folded.append(candidate.strip())
        return " ".join(folded)
    raise AssertionError(f"Schluessel '{key}' im Block nicht gefunden")


def _normalize_condition(raw: str) -> str:
    """Reduziert einen Ausdruck auf seinen Inhalt.

    Entfernt die optionale `${{ }}`-Klammerung und normalisiert Whitespace,
    damit `if:` und `env:` — die sich in genau dieser Klammerung
    unterscheiden muessen — vergleichbar werden.
    """
    without_braces = re.sub(r"\$\{\{|\}\}", " ", raw)
    return " ".join(without_braces.split())


def _step_names(block: list[str]) -> list[str]:
    return [
        line.strip()[len("- name:") :].strip()
        for line in block
        if line.strip().startswith("- name:")
    ]


def _step_block(block: list[str], step_name: str) -> list[str]:
    """Isoliert die Zeilen eines Steps bis zum Beginn des naechsten Steps."""
    for index, line in enumerate(block):
        if line.strip() != f"- name: {step_name}":
            continue
        step_indent = _indent_of(line)
        collected = [line]
        for candidate in block[index + 1 :]:
            if candidate.strip().startswith("- name:") and _indent_of(candidate) <= step_indent:
                break
            collected.append(candidate)
        return collected
    raise AssertionError(
        f"Step '{step_name}' nicht gefunden. Vorhanden: {_step_names(block)}"
    )


def test_upload_step_is_gated_on_the_artifact_condition() -> None:
    """Der Upload laeuft nicht mehr bedingungslos.

    Ohne diesen Guard schiebt jeder PR-Lauf einen mehrere Gigabyte grossen
    Tar durch den Runner, den anschliessend kein Job abholt.
    """
    step = _step_block(_job_block(BUILD_JOB), UPLOAD_STEP_NAME)
    condition = _scalar_value(step, "if")

    assert condition == EXPECTED_STEP_GUARD, (
        f"'{UPLOAD_STEP_NAME}' muss auf `if: {EXPECTED_STEP_GUARD}` stehen, "
        f"gefunden: `{condition}`"
    )


def test_artifact_condition_matches_the_only_consumer() -> None:
    """`IMAGE_ARTIFACT_NEEDED` und `prod-proxy-smoke.if` sind deckungsgleich.

    Diese Bedingung ist die einzige Verbindung zwischen Produzent und
    Konsument des Artefakts. Driftet sie auseinander, laeuft der Smoke-Test
    vor dem Registry-Push in einen fehlenden Download.
    """
    producer = _normalize_condition(_scalar_value(_job_block(BUILD_JOB), ENV_KEY))
    consumer = _normalize_condition(_scalar_value(_job_block(SMOKE_JOB), "if"))

    assert producer == consumer, (
        "Die Upload-Bedingung im Job 'build-only' und der if:-Guard von "
        "'prod-proxy-smoke' sind auseinandergelaufen.\n"
        f"  build-only.env.{ENV_KEY}: {producer}\n"
        f"  {SMOKE_JOB}.if:            {consumer}"
    )


def test_sbom_upload_stays_unconditional() -> None:
    """Nur der Image-Tar ist gegated, nicht die SBOM.

    Die SBOM ist klein, wird 90 Tage aufbewahrt und ist auf einem PR-Lauf
    der einzige verwertbare Nachweis darueber, was im Image steckt. Ein zu
    breit gezogener Guard haette sie stillschweigend mitgenommen.
    """
    step = _step_block(_job_block(BUILD_JOB), "SBOM als Artefakt hochladen")

    assert not any(line.strip().startswith("if:") for line in step), (
        "Der SBOM-Upload darf keine if:-Bedingung tragen — er soll auf "
        "jedem Lauf entstehen."
    )

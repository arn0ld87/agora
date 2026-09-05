"""Issue #1290 — ``LLM_MODEL_PRESETS`` liefert i18n-Schluessel statt Klartext.

Vorher trug jeder Eintrag ein fertiges ``label`` ("Qwen 2.5 14B (lokal,
GPU-arm)"). ``/api/simulation/available-models`` reichte den String durch und
``useEnvForm.ts`` rendert ihn unveraendert — der Text lief damit komplett am
``vue-i18n``-Katalog vorbei: bei Locale ``en`` stand weiter Deutsch im
Dropdown, und eine Textkorrektur brauchte einen Backend-Deploy.

Dieser Test ist der Drift-Waechter fuer die einzige Stelle, an der beide
Schichten aufeinandertreffen: der Schluessel wird im Backend vergeben, der Text
liegt im Frontend. Ohne ihn faellt ein neues Preset ohne Locale-Eintrag erst im
UI auf — als roher Schluessel bzw. als roher Modellname.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from unittest.mock import patch

import pytest
from flask import Flask

from app.api import simulation_bp
from app.config import Config

LABEL_KEY_PATTERN = re.compile(r"^llm\.preset\.(cloud|ollama|bedrock)\.[a-z0-9_]+$")

_REPO_ROOT = Path(__file__).resolve().parents[3]
_LOCALE_DIR = _REPO_ROOT / "frontend" / "src" / "i18n" / "locales"
LOCALE_FILES = ("de.json", "en.json")


@pytest.fixture
def app(monkeypatch):
    monkeypatch.delenv("AGORA_AUTH_TOKEN", raising=False)
    flask_app = Flask(__name__)
    from app.utils.api_responses import install_api_error_handlers

    install_api_error_handlers(flask_app)
    flask_app.register_blueprint(simulation_bp, url_prefix="/api/simulation")
    flask_app.config["TESTING"] = True
    flask_app.config["AGORA_AUTH_TOKEN"] = ""
    flask_app.extensions["neo4j_storage"] = None
    flask_app.extensions["neo4j_storage_error"] = None
    return flask_app


@pytest.fixture
def client(app):
    return app.test_client()


def _presets() -> list[dict]:
    return list(Config.LLM_MODEL_PRESETS or [])


def _load_locale(filename: str) -> dict:
    path = _LOCALE_DIR / filename
    assert path.is_file(), (
        f"Locale-Datei {path} fehlt. Der Pfad ist der Vertrag zwischen "
        f"Config.LLM_MODEL_PRESETS['label_key'] und dem vue-i18n-Katalog."
    )
    return json.loads(path.read_text(encoding="utf-8"))


def _resolve(catalog: dict, dotted_key: str):
    node = catalog
    for part in dotted_key.split("."):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node


def test_presets_are_not_empty():
    """Guard gegen einen leeren Katalog — sonst gruent alles darunter trivial."""
    assert _presets(), "Config.LLM_MODEL_PRESETS ist leer"


def test_every_preset_carries_a_label_key():
    missing = [p.get("name") for p in _presets() if not p.get("label_key")]
    assert not missing, f"Presets ohne label_key: {missing}"


def test_no_preset_carries_hardcoded_label_text():
    """``label`` ist der alte Klartext-Pfad und darf nicht zurueckkehren."""
    offenders = [p.get("name") for p in _presets() if "label" in p]
    assert not offenders, (
        f"Presets mit hartkodiertem label: {offenders}. "
        f"Anzeigetexte gehoeren nach frontend/src/i18n/locales/, nicht in config.py."
    )


def test_label_keys_follow_the_naming_scheme():
    bad = [
        (p.get("name"), p.get("label_key"))
        for p in _presets()
        if not LABEL_KEY_PATTERN.match(p.get("label_key") or "")
    ]
    assert not bad, f"label_key verletzt llm.preset.<kind>.<slug>: {bad}"


def test_label_key_kind_segment_matches_the_preset_kind():
    mismatched = [
        (p.get("name"), p.get("kind"), p.get("label_key"))
        for p in _presets()
        if (p.get("label_key") or "").split(".")[2:3] != [p.get("kind")]
    ]
    assert not mismatched, f"kind-Segment passt nicht zu preset['kind']: {mismatched}"


def test_label_keys_are_unique():
    keys = [str(p.get("label_key")) for p in _presets()]
    duplicates = sorted({k for k in keys if keys.count(k) > 1})
    assert not duplicates, f"Doppelte label_key-Werte: {duplicates}"


@pytest.mark.parametrize("locale_file", LOCALE_FILES)
def test_every_label_key_resolves_in_every_locale(locale_file: str):
    catalog = _load_locale(locale_file)
    unresolved = []
    for preset in _presets():
        key = preset.get("label_key")
        value = _resolve(catalog, key) if key else None
        if not isinstance(value, str) or not value.strip():
            unresolved.append(key)
    assert not unresolved, (
        f"{locale_file} loest diese label_key-Werte nicht auf: {unresolved}. "
        f"Ohne Eintrag faellt das UI auf den rohen Modellnamen zurueck."
    )


def test_available_models_endpoint_emits_label_keys(client, monkeypatch):
    """Der Endpunkt reicht ``label_key`` durch und erfindet kein ``label``."""
    monkeypatch.setattr(
        Config,
        "LLM_MODEL_PRESETS",
        [
            {
                "name": "zai.glm-4.7-flash",
                "label_key": "llm.preset.bedrock.glm_4_7_flash",
                "kind": "bedrock",
            }
        ],
        raising=False,
    )

    # Ollama-Tags-Probe abklemmen — der Test prueft den Preset-Durchreicher,
    # nicht die Erreichbarkeit eines lokalen Ollama.
    with patch("requests.get", side_effect=ConnectionError("kein Ollama im Test")):
        resp = client.get("/api/simulation/available-models")
    assert resp.status_code == 200

    presets = (resp.get_json() or {}).get("data", {}).get("presets") or []
    assert len(presets) == 1
    assert presets[0]["label_key"] == "llm.preset.bedrock.glm_4_7_flash"
    assert "label" not in presets[0]

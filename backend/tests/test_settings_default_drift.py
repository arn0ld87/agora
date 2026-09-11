"""
Drift-Gate: dasselbe Setting darf nicht drei verschiedene Defaults haben.

`LLM_MODEL_NAME` stand als `''` in `app/config.py` und in `SETTINGS_FIELDS`,
aber als `'qwen2.5:32b'` in `AgoraSettings` — obwohl deren Docstring
ausdruecklich behauptet, `config.py` 1:1 zu spiegeln. Der bestehende Pin-Test
in `test_settings_layer.py` vergleicht nur `SETTINGS_FIELDS` gegen eine
Literalliste; `AgoraSettings` war an keiner Stelle dagegen abgesichert, und
genau dort ist der Drift entstanden.

Verglichen werden ausschliesslich **deklarierte** Defaults, nie aufgeloeste
Werte: `Config` belegt seine Klassenattribute beim Import aus `os.environ`
(inklusive `.env`), taugt also nicht als Default-Anker. `Config` haengt
transitiv ueber die Literalliste in `test_settings_layer.py` mit drin.
"""

from __future__ import annotations

import pytest
from pydantic_core import PydanticUndefined

from app.services.settings_schema import SETTINGS_FIELDS
from app.settings import AgoraSettings


def _declared_defaults() -> dict[str, object]:
    """Env-Alias → deklarierter Default aus AgoraSettings."""
    defaults: dict[str, object] = {}
    for name, field in AgoraSettings.model_fields.items():
        alias = field.alias or name.upper()
        if field.default is PydanticUndefined:
            # default_factory-Felder (z. B. JSON-Dicts) haben keinen
            # vergleichbaren Skalar-Default.
            continue
        value = field.default
        if hasattr(value, "get_secret_value"):
            value = value.get_secret_value()
        defaults[alias] = value
    return defaults


DECLARED = _declared_defaults()
SHARED_KEYS = sorted(
    spec.key for spec in SETTINGS_FIELDS if spec.key in DECLARED
)


def test_surfaces_actually_overlap():
    """Schutz vor einem Test, der still nichts mehr vergleicht.

    Wuerde ein Refactor die Aliase umbenennen, faende die Parametrisierung
    unten keine Paare mehr und waere ab dann gruen ohne Aussage.
    """
    assert len(SHARED_KEYS) >= 25, (
        f"nur {len(SHARED_KEYS)} gemeinsame Keys gefunden — "
        "Alias-Mapping zwischen AgoraSettings und SETTINGS_FIELDS pruefen"
    )


@pytest.mark.parametrize("key", SHARED_KEYS)
def test_all_settings_surfaces_share_same_defaults(key: str):
    spec = next(s for s in SETTINGS_FIELDS if s.key == key)
    schema_default = spec.default
    settings_default = DECLARED[key]

    if spec.secret:
        # Secrets modellieren "nicht gesetzt" unterschiedlich: der
        # Settings-Layer als leeren String, AgoraSettings als `None`
        # (`SecretStr | None`). Das ist eine Typ-, keine Wertaussage — beide
        # bedeuten "kein Wert hinterlegt".
        assert not schema_default and not settings_default, (
            f"{key}: Secret-Felder duerfen auf keiner Flaeche einen "
            f"vorbelegten Wert haben "
            f"(SETTINGS_FIELDS={schema_default!r}, AgoraSettings={settings_default!r})"
        )
        return

    assert settings_default == schema_default, (
        f"{key} hat abweichende Defaults: "
        f"AgoraSettings={settings_default!r} vs SETTINGS_FIELDS={schema_default!r}. "
        "Beide Flaechen beschreiben dasselbe Setting — einen Wert waehlen, "
        "nicht beide pflegen."
    )

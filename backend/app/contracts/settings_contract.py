"""Runtime-Settings contracts for the live settings API.

The read-path stays declarative in ``settings_schema.py`` because the UI needs
section/source metadata per field. The write-path, however, benefits from a
strict Pydantic boundary so unknown keys and unexpected nested payloads fail
fast with ``extra="forbid"`` before the domain validator handles ranges and
cross-field rules.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, create_model

from ..services.settings_schema import SETTINGS_FIELDS

_TYPE_MAP: dict[str, type[Any]] = {
    'string': str,
    'enum': str,
    'int': int,
    'float': float,
    'bool': bool,
}


def _build_patch_model(*, secret: bool | None) -> type[BaseModel]:
    fields: dict[str, tuple[Any, None]] = {}
    for spec in SETTINGS_FIELDS:
        if secret is not None and spec.secret is not secret:
            continue
        fields[spec.key] = (_TYPE_MAP.get(spec.type, str) | None, None)
    return create_model(
        (
            'RuntimeSettingsSecretFieldsModel'
            if secret is True
            else 'RuntimeSettingsPatchModel'
            if secret is False
            else 'RuntimeSettingsAnyFieldsModel'
        ),
        __config__=ConfigDict(extra='forbid'),
        **fields,
    )


RuntimeSettingsPatchModel = _build_patch_model(secret=False)
RuntimeSettingsAnyFieldsModel = _build_patch_model(secret=None)
RuntimeSettingsSecretFieldsModel = _build_patch_model(secret=True)


class RuntimeSettingsSecretsPayloadModel(BaseModel):
    model_config = ConfigDict(extra='forbid')

    confirm: bool
    fields: RuntimeSettingsSecretFieldsModel

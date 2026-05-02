"""Settings-Payload-Validator (Issue #133, SUB2).

Wird vom ``PUT /api/settings``-Endpunkt aufgerufen. Bewusst kein
Pydantic-Model: die Schema-Source-of-Truth liegt in
:data:`settings_schema.SETTINGS_FIELDS` (FieldSpec-Liste); ein zweites
Pydantic-Model wäre Doppelpflege. Dieser Validator interpretiert die
FieldSpec direkt — gleiche Regeln wie der Startup-Check
(``Config.validate``), insbesondere die ``EMBEDDING_MODEL`` ↔
``VECTOR_DIM``-Konsistenz via :func:`app.config.infer_vector_dim_for_model`.

Public Interface:

    validate_payload(payload: Mapping, *, allow_secrets: bool=False)
        -> tuple[dict[str, Any], list[ValidationError]]

Bei nicht-leerer Error-Liste schreibt der Aufrufer **nichts** und liefert
HTTP 400 zurück — der Service hält das in
``SettingsService.apply_payload`` als All-or-Nothing-Vertrag durch.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from ..config import infer_vector_dim_for_model
from .settings_schema import SETTINGS_FIELDS, FieldSpec, field_by_key


@dataclass(frozen=True)
class ValidationError:
    """Strukturierter Validation-Fehler.

    ``key`` kann leer sein für Cross-Field-Errors (z. B. wenn nur die
    Kombination zweier Werte das Problem ist) — Frontend zeigt diese
    Errors dann als Banner statt als Field-Hint.
    """

    key: str
    message: str
    code: str

    def to_dict(self) -> dict[str, str]:
        return {'key': self.key, 'message': self.message, 'code': self.code}


# ---------------------------------------------------------------------------
# Coercion (per-Field-Typ)
# ---------------------------------------------------------------------------


_BOOL_TRUE = frozenset({'true', '1', 'yes', 'on'})
_BOOL_FALSE = frozenset({'false', '0', 'no', 'off'})


def _coerce_int(spec: FieldSpec, raw: Any) -> tuple[int | None, str | None]:
    if isinstance(raw, bool):
        # bool ist subclass von int — wir wollen das hier explizit
        # ablehnen, sonst landet ``true`` als 1 in einem int-Feld.
        return None, f'{spec.key}: erwarte int, bool erhalten'
    try:
        # ``int(0.5)`` würde lautlos auf 0 trunken; das ist nicht das,
        # was der Operator im UI eingibt. Wir akzeptieren nur ganze
        # Floats und Strings, die int-parsen.
        if isinstance(raw, float):
            if raw != int(raw):
                return None, f'{spec.key}: erwarte int, fraktionalen float erhalten'
            return int(raw), None
        return int(raw), None
    except (TypeError, ValueError):
        return None, f'{spec.key}: ungültiger int-Wert {raw!r}'


def _coerce_float(spec: FieldSpec, raw: Any) -> tuple[float | None, str | None]:
    if isinstance(raw, bool):
        return None, f'{spec.key}: erwarte float, bool erhalten'
    try:
        return float(raw), None
    except (TypeError, ValueError):
        return None, f'{spec.key}: ungültiger float-Wert {raw!r}'


def _coerce_bool(spec: FieldSpec, raw: Any) -> tuple[bool | None, str | None]:
    if isinstance(raw, bool):
        return raw, None
    if isinstance(raw, (int, float)):
        # Nur 0/1 akzeptieren — alles andere ist mehrdeutig.
        if raw == 0:
            return False, None
        if raw == 1:
            return True, None
        return None, f'{spec.key}: erwarte bool, ungültige Zahl {raw!r}'
    if isinstance(raw, str):
        s = raw.strip().lower()
        if s in _BOOL_TRUE:
            return True, None
        if s in _BOOL_FALSE:
            return False, None
        return None, f'{spec.key}: erwarte bool, ungültiger string {raw!r}'
    return None, f'{spec.key}: erwarte bool, {type(raw).__name__} erhalten'


def _coerce_string(spec: FieldSpec, raw: Any) -> tuple[str | None, str | None]:
    if isinstance(raw, bool):
        # bool akzeptieren wir nicht als string — das wäre fast immer
        # ein Frontend-Bug.
        return None, f'{spec.key}: erwarte string, bool erhalten'
    if raw is None:
        # Leerstring ist legitim (z. B. AGORA_AUTH_TOKEN unset);
        # ``None`` interpretieren wir als „Feld weglassen", nicht als
        # „auf leer setzen". Aufrufer hat den Key dann gar nicht im
        # Payload.
        return None, f'{spec.key}: null als Wert nicht erlaubt — Feld weglassen, um den Default wiederherzustellen'
    return str(raw), None


def _coerce_enum(spec: FieldSpec, raw: Any) -> tuple[str | None, str | None]:
    s, err = _coerce_string(spec, raw)
    if err:
        return None, err
    assert s is not None
    if spec.enum_values and s not in spec.enum_values:
        allowed = ', '.join(spec.enum_values)
        return None, f'{spec.key}: ungültiger enum-Wert {s!r} (erlaubt: {allowed})'
    return s, None


def _coerce(spec: FieldSpec, raw: Any) -> tuple[Any, str | None]:
    if spec.type == 'int':
        return _coerce_int(spec, raw)
    if spec.type == 'float':
        return _coerce_float(spec, raw)
    if spec.type == 'bool':
        return _coerce_bool(spec, raw)
    if spec.type == 'enum':
        return _coerce_enum(spec, raw)
    return _coerce_string(spec, raw)


def _check_range(spec: FieldSpec, value: Any) -> str | None:
    if spec.type not in ('int', 'float'):
        return None
    if spec.min_value is not None and value < spec.min_value:
        return f'{spec.key}: {value} unterschreitet Minimum {spec.min_value}'
    if spec.max_value is not None and value > spec.max_value:
        return f'{spec.key}: {value} überschreitet Maximum {spec.max_value}'
    return None


# ---------------------------------------------------------------------------
# Cross-Field-Regeln
# ---------------------------------------------------------------------------


def _check_embedding_consistency(validated: dict[str, Any]) -> ValidationError | None:
    """``VECTOR_DIM`` muss zur Output-Dim des ``EMBEDDING_MODEL``
    passen — gleiche Regel wie ``Config.validate()`` beim Startup.

    Nur greifen, wenn beide Werte im Payload sind ODER mindestens einer
    plus der bisher persistierte Gegenpart bekannt ist. Im Validator
    ohne State greifen wir nur bei beiden im Payload; den State-
    abhängigen Check übernimmt der Service-Layer.
    """
    if 'EMBEDDING_MODEL' in validated and 'VECTOR_DIM' in validated:
        model = validated['EMBEDDING_MODEL']
        dim = validated['VECTOR_DIM']
        expected = infer_vector_dim_for_model(model)
        if expected is not None and dim != expected:
            return ValidationError(
                key='VECTOR_DIM',
                code='vector_dim_mismatch',
                message=(
                    f'VECTOR_DIM {dim} passt nicht zu EMBEDDING_MODEL '
                    f'{model!r} (erwartet {expected}).'
                ),
            )
    return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def validate_payload(
    payload: Mapping[str, Any],
    *,
    allow_secrets: bool = False,
) -> tuple[dict[str, Any], list[ValidationError]]:
    """Validiert ein flaches ``{key: value}``-Payload.

    Args:
        payload: Dict im JSON-Body-Format. Unbekannte Keys → Error.
        allow_secrets: Wenn ``False`` (Default), werden Secret-Felder
            mit ``code='secret_not_allowed'`` abgelehnt — der reguläre
            ``PUT /api/settings``-Endpunkt nutzt das, um Secrets auf
            den dedizierten Endpunkt zu zwingen.

    Returns:
        ``(validated, errors)``. Bei nicht-leerer ``errors``-Liste ist
        ``validated`` *möglicherweise unvollständig* — der Aufrufer
        muss alle-or-nothing entscheiden.
    """
    validated: dict[str, Any] = {}
    errors: list[ValidationError] = []

    if not isinstance(payload, Mapping):
        return {}, [ValidationError(
            key='', code='invalid_payload',
            message='Payload muss ein JSON-Object sein.',
        )]

    for key, raw_value in payload.items():
        if not isinstance(key, str):
            errors.append(ValidationError(
                key=str(key), code='invalid_key',
                message=f'Key {key!r} ist kein String.',
            ))
            continue

        spec = field_by_key(key)
        if spec is None:
            errors.append(ValidationError(
                key=key, code='unknown_field',
                message=f'Unbekanntes Settings-Feld: {key}',
            ))
            continue

        if spec.secret and not allow_secrets:
            errors.append(ValidationError(
                key=key, code='secret_not_allowed',
                message=(
                    f'{key} ist ein Secret-Feld und kann nicht über '
                    'PUT /api/settings gesetzt werden — bitte den '
                    'Secrets-Endpunkt benutzen.'
                ),
            ))
            continue

        coerced, err = _coerce(spec, raw_value)
        if err:
            errors.append(ValidationError(
                key=key, code='type_error', message=err
            ))
            continue

        range_err = _check_range(spec, coerced)
        if range_err:
            errors.append(ValidationError(
                key=key, code='out_of_range', message=range_err
            ))
            continue

        validated[key] = coerced

    cross = _check_embedding_consistency(validated)
    if cross is not None:
        errors.append(cross)

    return validated, errors


def split_payload_by_secret(
    payload: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Hilfsfunktion: trennt den Body in (non-secret, secret).

    Wird intern vom Settings-Layer verwendet, wenn der Aufrufer beide
    Pfade gemischt geliefert hat — der Validator selbst lehnt das
    bereits ab, aber der Helper ist nützlich für Tests und für eine
    künftige Optimierung „atomic write of file (non-secret only)".
    """
    secrets: dict[str, Any] = {}
    nonsecret: dict[str, Any] = {}
    for key, value in payload.items():
        spec = field_by_key(str(key))
        if spec is not None and spec.secret:
            secrets[key] = value
        else:
            nonsecret[key] = value
    return nonsecret, secrets


# Re-export für Aufrufer, die nur die Liste der Field-Keys brauchen.
ALL_FIELD_KEYS: tuple[str, ...] = tuple(spec.key for spec in SETTINGS_FIELDS)

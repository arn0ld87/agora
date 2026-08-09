"""Deterministische, run-lokale Identitaet fuer Evidence-Records."""

from __future__ import annotations

import hashlib
from enum import Enum


def _identity_part(value: object, *, field_name: str) -> str:
    if isinstance(value, Enum):
        value = value.value
    normalized = str(value).strip()
    if not normalized:
        raise ValueError(f"{field_name} darf nicht leer sein.")
    return normalized


def build_evidence_id(
    scope_id: str,
    source_kind: str,
    producer_key: str,
) -> str:
    """Baut ``ev_<128-bit-hex>`` ohne Inhaltstext als Identitaetsmaterial."""

    parts = (
        _identity_part(scope_id, field_name="scope_id"),
        _identity_part(source_kind, field_name="source_kind"),
        _identity_part(producer_key, field_name="producer_key"),
    )
    material = b"".join(
        len(part.encode("utf-8")).to_bytes(4, "big") + part.encode("utf-8")
        for part in parts
    )
    return f"ev_{hashlib.sha256(material).hexdigest()[:32]}"


__all__ = ["build_evidence_id"]

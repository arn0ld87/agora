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


def build_producer_key(prefix: str, *parts: object) -> str:
    """Baut einen deterministischen ``producer_key`` aus strukturierten Teilen.

    Laengen-Praefix pro Teil verhindert Kollisionen durch Konkatenation
    (``("ab", "c")`` vs. ``("a", "bc")``). Der Praefix bleibt lesbar, der
    Hash haelt den Key unter dem 500-Zeichen-Limit von
    ``EvidenceRecordModel.producer_key``.
    """
    normalized = tuple(
        _identity_part(part, field_name=f"producer_key part {index}")
        for index, part in enumerate(parts)
    )
    if not normalized:
        raise ValueError("build_producer_key braucht mindestens einen Teil.")
    material = b"".join(
        len(part.encode("utf-8")).to_bytes(4, "big") + part.encode("utf-8")
        for part in normalized
    )
    digest = hashlib.sha256(material).hexdigest()[:24]
    clean_prefix = _identity_part(prefix, field_name="prefix")
    return f"{clean_prefix}:{digest}"


__all__ = ["build_evidence_id", "build_producer_key"]

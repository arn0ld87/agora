"""Persistenzmodell für Personasätze (Issue #1807, Etappe 7).

Derselbe Schnitt wie bei ``agora.projects`` und ``agora.simulations``: die
Felder, nach denen gefiltert, sortiert oder gesperrt wird, bekommen eine
eigene Spalte, alles Übrige liegt in ``payload`` (Beschreibung, Einträge,
``used_by_simulation_ids``, ``schema_version``). Die Struktur von ``payload``
garantiert der Vertrag (``app/contracts/persona_set_contract.py``), nicht das
Schema.

Festlegungen, die keine Nachlässigkeit sind:

``id`` ist ``Text`` (Form ``pset_<12 Hexstellen>``), ``created_at``,
``updated_at`` und ``locked_at`` sind ``Text`` — der Vertrag führt
ISO-8601-Zeichenketten, und ein Umweg über ``timestamptz`` gäbe beim
Zurücklesen eine andere Zeichenkette.

``graph_id`` und ``project_id`` sind **reine Verweise ohne Fremdschlüssel**:
ein Personasatz gehört der Bibliothek, nicht dem Graphen. Er überlebt das
Löschen von Graph und Projekt, und er ist ohne beide anlegbar (manuell,
KI-Entwurf). Deshalb hängt ``AGORA_PERSONA_SET_BACKEND=postgres`` auch von
keinem anderen Schalter ab.

``locked_at`` hat eine eigene Spalte, weil die Sperre die zentrale Bedingung
für Schreibzugriffe ist; ``mark_used`` setzt sie atomar mit
``used_by_simulation_ids``.

``workspace_id`` ist ``NOT NULL`` von Anfang an (ADR-0018): die Tabelle ist
neu, es gibt keinen Bestand, der erst dem Default-Workspace zugeordnet werden
müsste. RLS-Policy siehe Migration.
"""
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import CheckConstraint, ForeignKey, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import AGORA_SCHEMA, Base


class PersonaSetModel(Base):
    """Ein Personasatz: Kernspalten plus ``payload`` für den Rest des Vertrags."""

    __tablename__ = 'persona_sets'
    __table_args__ = (
        CheckConstraint('char_length(id) > 0', name='id_not_empty'),
        CheckConstraint('char_length(name) > 0', name='name_not_empty'),
        # Wie bei den übrigen Tabellen (Ziel möglicher zusammengesetzter
        # Fremdschlüssel; Plan §18).
        UniqueConstraint('id', 'workspace_id'),
        {'schema': AGORA_SCHEMA},
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f'{AGORA_SCHEMA}.workspaces.id'),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    graph_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    project_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    #: ``None`` = bearbeitbar. Gesetzt vom ersten ``mark_used``.
    locked_at: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[str] = mapped_column(Text, nullable=False)

    #: Alle Vertragsfelder, die keine eigene Spalte haben.
    payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )

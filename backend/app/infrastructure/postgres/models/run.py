"""Persistenzmodell für Run-Manifeste (docs/plans/supabase.md §11, PR 8).

Anders als bei ``agora.projects`` und ``agora.simulations`` ist ``payload``
hier das **vollständige Manifest** und die übrigen Spalten sind Projektionen
daraus. Der Grund ist der Vertrag: ``RunRecord.to_manifest()`` schreibt nur
gesetzte Felder (``exclude_unset``) und unterscheidet damit "fehlt" von
"steht auf ``null``". Ein Altbestand ohne ``completed_at`` muss ohne
``completed_at`` zurückkommen, einer mit ``"completed_at": null`` mit. Eine
Spalte kann diesen Unterschied nicht tragen, das ``payload`` schon.

Die Spalten gibt es trotzdem, weil nach ihnen sortiert, gefiltert und
verknüpft wird. Sie werden bei jedem Schreiben aus dem Manifest abgeleitet,
nie getrennt gepflegt.

Festlegungen, die vom Plantext abweichen und keine Nachlässigkeit sind:

``id`` ist ``Text`` und nicht ``uuid``. Die Kennung hat das Format
``run_<12 hex>`` und steht in API-Pfaden, Logs und Event-Streams.

``started_at``, ``updated_at`` und ``completed_at`` sind ``Text`` — derselbe
Grund wie bei Projekten und Simulationen: der Vertrag führt
ISO-8601-Zeichenketten, ein Umweg über ``timestamptz`` gäbe beim Zurücklesen
eine andere Zeichenkette.

``simulation_id`` ist ein Fremdschlüssel auf ``agora.simulations(id)`` und
**nullable**: Graph-Build-Runs haben keine Simulation. Der Wert stammt aus
``linked_ids.simulation_id``. ``ON DELETE SET NULL``, damit die Run-Historie
eine gelöschte Simulation überlebt — wie bei der Dateiablage, in der das
Manifest liegen bleibt.

``status`` bekommt **keinen** Check-Constraint. ``RunRecord`` nimmt bewusst
jeden Status an (Altbestand); die Kanonisierung macht
``RunRegistry.canonical_status`` beim Schreiben.

Lease und Heartbeat (``metadata.worker_*``, ``heartbeat_at``) bekommen keine
eigene Spalte. Sie sind Laufzeitzustand und bleiben, wo der Vertrag sie
hinlegt: im Manifest.

Es gibt **kein** ``workspace_id``. Multi-User ist eine eigene, freizugebende
Phase.
"""
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import CheckConstraint, ForeignKey, ForeignKeyConstraint, Index, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import AGORA_SCHEMA, Base


class RunModel(Base):
    """Single-User-Modell ohne Workspace- oder Auth-Abhängigkeiten."""

    __tablename__ = 'runs'
    __table_args__ = (
        CheckConstraint(
            'char_length(id) > 0',
            name='id_not_empty',
        ),
        # ``list_runs(simulation_id=...)`` und der Report-Status lesen danach.
        Index('ix_runs_simulation_id', 'simulation_id'),
        # Verweis nur innerhalb desselben Workspace. ``SET NULL (simulation_id)``
        # löst nur den Verweis; ``workspace_id`` bleibt (PostgreSQL ≥ 15).
        ForeignKeyConstraint(
            ['simulation_id', 'workspace_id'],
            [f'{AGORA_SCHEMA}.simulations.id', f'{AGORA_SCHEMA}.simulations.workspace_id'],
            ondelete='SET NULL (simulation_id)',
        ),
        {'schema': AGORA_SCHEMA},
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    # Workspace der Zeile (ADR-0018, #1614). Der Bestand vor #1614 steht im
    # Default-Workspace; Löschen eines Workspace mit Daten scheitert.
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f'{AGORA_SCHEMA}.workspaces.id'),
        nullable=False,
        index=True,
    )
    run_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    entity_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str | None] = mapped_column(Text, nullable=True)
    simulation_id: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    started_at: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[str | None] = mapped_column(Text, nullable=True)
    completed_at: Mapped[str | None] = mapped_column(Text, nullable=True)

    #: Das vollständige Manifest aus ``RunRecord.to_manifest()``.
    payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )

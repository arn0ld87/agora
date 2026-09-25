"""Persistenzmodell für Projekt-Metadaten (docs/plans/supabase.md §11, PR 6).

Der Spaltenschnitt ist die am Gate getroffene Entscheidung: die Felder, nach
denen abgefragt oder sortiert wird, bekommen eine eigene Spalte, alles Übrige
liegt in ``payload``. Die Struktur von ``payload`` garantiert der
Pydantic-Vertrag (``app/contracts/project_contract.py``), nicht das Schema —
das ist die bewusste Gegenleistung dafür, dass eine neue Feldbelegung keine
Migration kostet.

Drei Festlegungen weichen vom Plan ab und sind keine Nachlässigkeit:

``id`` ist ``Text`` und nicht ``uuid``. Die Kennung ist zugleich der
Verzeichnisname unter ``uploads/projects/<project_id>/``, wo die Artefakte
liegen. Ein Formatwechsel bräche jeden bestehenden Pfad.

``created_at`` und ``updated_at`` sind ``Text`` und nicht ``timestamptz``. Der
Vertrag typisiert sie als ISO-8601-Zeichenketten, weil die Dateiablage sie so
schreibt; ``list`` sortiert lexikografisch darüber, was für dieses Format
chronologisch ist. Über ``timestamptz`` gelesen käme eine **andere**
Zeichenkette zurück — eine naive Zeitangabe bekäme beim Schreiben die
Sitzungszeitzone und beim Lesen einen Versatz —, und der Datensatz wäre nicht
mehr zeichengleich zur Datei. Wenn der Vertrag später auf ``datetime``
umstellt, folgt die Spalte; vorher nicht.

Es gibt **kein** ``workspace_id``. Multi-User ist eine eigene, freizugebende
Phase; der Weg zum Nachrüsten steht in der Entscheidung
„workspace_id kommt später" des Plans.
"""
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import CheckConstraint, ForeignKey, Index, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import AGORA_SCHEMA, Base

#: Die Statuswerte des Vertrags. Als Check-Constraint gespiegelt, damit die
#: Tabelle nicht auf die Anwendung vertrauen muss — ein Wert, den der Vertrag
#: ablehnt, soll auch die Datenbank ablehnen.
PROJECT_STATUS_VALUES = (
    'created',
    'ontology_generated',
    'graph_building',
    'graph_completed',
    'graph_incomplete',
    'failed',
)

_STATUS_IN_LIST = ', '.join(f"'{value}'" for value in PROJECT_STATUS_VALUES)


class ProjectModel(Base):
    """Single-User-Modell ohne Workspace- oder Auth-Abhängigkeiten."""

    __tablename__ = 'projects'
    __table_args__ = (
        CheckConstraint(
            'char_length(id) > 0',
            name='id_not_empty',
        ),
        CheckConstraint(
            f'status IN ({_STATUS_IN_LIST})',
            name='status_known',
        ),
        # Die Projektliste zeigt das Neueste oben und ist der einzige
        # Lesepfad, der über alle Zeilen geht.
        Index('ix_projects_created_at', text('created_at DESC')),
        # Ziel der zusammengesetzten Fremdschlüssel: ein Verweis kann nie
        # in einen anderen Workspace zeigen (Plan §18).
        UniqueConstraint('id', 'workspace_id'),
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
    name: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    graph_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    llm_profile_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[str] = mapped_column(Text, nullable=False)

    #: Alle Vertragsfelder, die keine eigene Spalte haben. Niemals Secrets:
    #: ``llm_provider`` trägt ausschliesslich ``redacted_metadata()``.
    payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )

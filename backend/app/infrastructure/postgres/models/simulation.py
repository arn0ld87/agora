"""Persistenzmodell für Simulationsmetadaten (docs/plans/supabase.md §11, PR 7).

Derselbe Schnitt wie bei ``agora.projects``: die Felder, nach denen gefiltert
oder verknüpft wird, bekommen eine eigene Spalte, alles Übrige liegt in
``payload``. Die Struktur von ``payload`` garantiert der Vertrag
(``app/contracts/simulation_record_contract.py``), nicht das Schema.

Festlegungen, die vom Plantext abweichen und keine Nachlässigkeit sind:

``id`` ist ``Text`` und nicht ``uuid``. Die Kennung ist zugleich der
Verzeichnisname unter ``uploads/simulations/<simulation_id>/``, wo
``simulation_config.json``, Profile und Logs liegen.

``created_at`` und ``updated_at`` sind ``Text`` — derselbe Grund wie bei den
Projekten: der Vertrag führt ISO-8601-Zeichenketten, und ein Umweg über
``timestamptz`` gäbe beim Zurücklesen eine andere Zeichenkette.

``project_id`` ist ein Fremdschlüssel auf ``agora.projects(id)`` und
**nullable**. Der Vertrag kennt ``''`` als "kein Projekt"; in der Spalte steht
dafür ``NULL``, weil eine leere Zeichenkette den Fremdschlüssel verletzen
würde. ``ON DELETE SET NULL``, weil ``ProjectManager.delete_project`` zuerst
das Artefaktverzeichnis entfernt und dann die Zeile: ein ``RESTRICT`` liesse
das Projekt ohne Dateien, aber mit Datensatz zurück. Mit der Dateiablage
bleibt eine Simulation beim Löschen ihres Projekts ebenfalls liegen.

``status`` bekommt **keinen** Check-Constraint. Die Statuswerte leben in
``SimulationStatus`` (``simulation_manager.py``) und nicht im Vertrag; ein
Constraint hier wäre eine zweite Liste, die niemand gegen die erste prüft.

Es gibt **kein** ``workspace_id``. Multi-User ist eine eigene, freizugebende
Phase.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import CheckConstraint, ForeignKey, Index, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from .base import AGORA_SCHEMA, Base


class SimulationModel(Base):
    """Single-User-Modell ohne Workspace- oder Auth-Abhängigkeiten."""

    __tablename__ = 'simulations'
    __table_args__ = (
        CheckConstraint(
            'char_length(id) > 0',
            name='id_not_empty',
        ),
        # ``list(project_id=...)`` ist der häufigste Lesepfad.
        Index('ix_simulations_project_id', 'project_id'),
        {'schema': AGORA_SCHEMA},
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    project_id: Mapped[str | None] = mapped_column(
        Text,
        ForeignKey(f'{AGORA_SCHEMA}.projects.id', ondelete='SET NULL'),
        nullable=True,
    )
    graph_id: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    source_simulation_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    root_simulation_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[str] = mapped_column(Text, nullable=False)

    #: Alle Vertragsfelder, die keine eigene Spalte haben.
    payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )

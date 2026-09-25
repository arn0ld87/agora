"""Persistenzmodell für Report-Metadaten (docs/plans/supabase.md §11, PR 9).

Derselbe Schnitt wie bei ``agora.runs``: ``payload`` ist der vollständige
Datensatz aus ``ReportRecord.to_dict()`` — der Inhalt von ``meta.json`` —,
die übrigen Spalten sind Projektionen daraus für Filter, Sortierung und den
Fremdschlüssel. Sie werden bei jedem Schreiben abgeleitet, nie getrennt
gepflegt. Damit überlebt der Datensatz auch ein ``ON DELETE SET NULL`` auf
``simulation_id`` unverändert.

Report-**Inhalte** (``report-v3.json``, ``outline.json``, ``section_XX.md``,
Evidence-Map, Logs; Plan §11 Klasse B) bleiben Dateien unter
``uploads/reports/<Ablageschlüssel>/``. Diese Tabelle hält nur die Metadaten.

Festlegungen, die vom Plantext abweichen und keine Nachlässigkeit sind:

``id`` ist der **Ablageschlüssel**, nicht zwingend die ``report_id`` im
Datensatz. Ein Altbestand kann unter ``report_deepseek_<hex>/`` liegen und
``report_<hex>`` eintragen; die Inhalte daneben findet nur der Schlüssel
(Codex-Review auf #1601). Für jeden neu geschriebenen Report sind beide
gleich. ``report_id`` steht deshalb zusätzlich als eigene Spalte.

``created_at`` und ``completed_at`` sind ``Text`` — der Vertrag führt
ISO-8601-Zeichenketten (``''`` für "noch nicht"), ein Umweg über
``timestamptz`` gäbe beim Zurücklesen eine andere Zeichenkette.

``simulation_id`` ist ein Fremdschlüssel auf ``agora.simulations(id)``,
**nullable** und ``ON DELETE SET NULL``: ein Report überlebt seine
Simulation, wie in der Dateiablage.

``status`` bekommt **keinen** Check-Constraint; die Statuswerte leben in
``ReportStatus`` (``app/models/report.py``), nicht im Vertrag.

Es gibt **kein** ``workspace_id``. Multi-User ist eine eigene, freizugebende
Phase.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import CheckConstraint, ForeignKey, Index, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from .base import AGORA_SCHEMA, Base


class ReportModel(Base):
    """Single-User-Modell ohne Workspace- oder Auth-Abhängigkeiten."""

    __tablename__ = 'reports'
    __table_args__ = (
        CheckConstraint(
            'char_length(id) > 0',
            name='id_not_empty',
        ),
        # ``get_report_by_simulation`` und die Simulationshistorie lesen danach.
        Index('ix_reports_simulation_id', 'simulation_id'),
        {'schema': AGORA_SCHEMA},
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    report_id: Mapped[str] = mapped_column(Text, nullable=False)
    simulation_id: Mapped[str | None] = mapped_column(
        Text,
        ForeignKey(f'{AGORA_SCHEMA}.simulations.id', ondelete='SET NULL'),
        nullable=True,
    )
    status: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[str | None] = mapped_column(Text, nullable=True)
    completed_at: Mapped[str | None] = mapped_column(Text, nullable=True)

    #: Der vollständige Datensatz aus ``ReportRecord.to_dict()``.
    payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )

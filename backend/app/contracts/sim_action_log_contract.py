"""Sim-Action-Log-Contract — Vertrag zwischen Log-Writer und Log-Reader.

Slice 6 · 2026-08-02 — Fix B-28 (``log_round_end`` schrieb keine Sim-Zeit).

Writer: ``backend/scripts/action_logger.py`` (läuft im Simulations-Subprozess)
Reader: ``backend/app/services/sim/action_log_reader.py``

Beide Seiten tauschten die Felder bisher über ein implizites Dict aus: der
Reader las ``simulated_hours``, der Writer schrieb den Schlüssel nie. In
``run_state.json`` stand deshalb dauerhaft ``simulated_hours: 0`` (#1014).
Dieser Vertrag ist die einzige Stelle, an der die Feldnamen des
``round_end``-Events definiert werden.

Reichweite des Fixes: Writer → Reader → ``SimulationRunState`` → Status-API.
Die Anzeige im Frontend ist laut #1014 ausdrücklich out of scope — sie liest
den Wert bis heute nicht (siehe #1018).

EINHEITEN — nicht verwechseln:

- ``simulated_minutes``: seit Simulationsstart verstrichene Sim-Zeit. Streng
  monoton wachsend über die Runden. Kanonische Einheit dieses Vertrags.
- ``simulated_hour`` (Singular, im ``round_start``-Event): Tages-Uhrzeit 0..23,
  berechnet mit ``% 24``. Springt bei Tageswechsel auf 0 zurück und taugt
  deshalb NICHT als Fortschrittswert.

Minuten sind kanonisch, weil ``minutes_per_round`` ganzzahlig in [30, 120]
liegt: ``round * minutes_per_round`` ist damit exakt und verlustfrei. Stunden
werden als ``float`` abgeleitet (30 min/Runde ⇒ 0.5 h). Eine int-Stunde würde
die Monotonie brechen — die Folge wäre 0, 1, 1, 2, … statt 0.5, 1.0, 1.5, 2.0.
"""

from __future__ import annotations

from typing import Any, Final, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

# ``Final`` statt blankem str: nur so leitet mypy den Literal-Typ ab und die
# Konstante taugt als Default des ``event_type``-Feldes.
EVENT_TYPE_ROUND_END: Final = "round_end"

MINUTES_PER_HOUR: Final = 60


class RoundEndEvent(BaseModel):
    """Ein ``round_end``-Eintrag des Action-Logs (eine JSONL-Zeile).

    ``extra="ignore"``: Der Reader muss auch Logs verarbeiten können, die eine
    neuere Writer-Version mit Zusatzfeldern geschrieben hat.
    """

    model_config = ConfigDict(extra="ignore")

    event_type: Literal["round_end"] = EVENT_TYPE_ROUND_END
    round: int = Field(default=0, ge=0, description="Rundennummer; 0 = Initial-Runde.")
    timestamp: str = ""
    actions_count: int = Field(default=0, ge=0)
    simulated_minutes: int = Field(
        default=0,
        ge=0,
        description="Seit Sim-Start verstrichene Minuten. Monoton wachsend.",
    )
    platform: str | None = None

    @field_validator("simulated_minutes", mode="before")
    @classmethod
    def _ganze_minuten(cls, value: Any) -> Any:
        """Rundet Fließkomma-Minuten auf ganze.

        ``run_parallel_simulation.py:2044`` lädt die Config im Subprozess roh
        über ``json.load`` — am Schema vorbei, das ``minutes_per_round`` auf
        ``int`` festlegt. Ein handgeschriebenes ``minutes_per_round: 45.5``
        erreicht den Writer damit als Float und ließe ``log_round_end`` an
        einer ValidationError sterben, wo vorher nur ein Dict geschrieben
        wurde. Runden statt Absturz.
        """
        if isinstance(value, float):
            return round(value)
        return value

    @property
    def simulated_hours(self) -> float:
        """Verstrichene Sim-Zeit in Stunden (float — 30 min ⇒ 0.5)."""
        return self.simulated_minutes / MINUTES_PER_HOUR

    @classmethod
    def from_log_entry(cls, data: dict[str, Any]) -> RoundEndEvent:
        """Parst einen Log-Eintrag, inklusive Alt-Logs ohne ``simulated_minutes``.

        Vor Slice 6 geschriebene Logs enthalten das Feld nicht — der alte
        Writer schrieb *keinen* Zeitschlüssel, auch nicht ``simulated_hours``;
        genau das ist die Prämisse von B-28. Solche Einträge fallen über
        ``Field(default=0)`` auf 0 Minuten, statt einen Fehler zu werfen: ein
        laufender Run darf an einem alten Eintrag nicht sterben.
        """
        return cls.model_validate(data)

    def to_log_entry(self) -> dict[str, Any]:
        """Serialisiert die JSONL-Zeile. ``platform=None`` wird weggelassen."""
        return self.model_dump(exclude_none=True)

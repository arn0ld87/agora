"""Belegdichte der Claims eines Berichts (Issue #1779, Schritt 2.1).

Beim Abschluss des Berichts wird gezählt, wie dicht seine Claims belegt sind:
wie viele Claims gar keinen, genau einen oder mehrere stützende Belege tragen,
wie viele davon auf unabhängigen Quellen beruhen und wie viele am
Ein-Quellen-Deckel (0,59) hängen. Eine Abnahme liest die Zahlen aus dem
Artefakt ``evidence_density.json`` im Berichtsverzeichnis, statt sie mit einem
Handskript nachzuzählen. Die Zählung ändert weder Confidence noch Status.
"""
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


class EvidenceDensity(BaseModel):
    """Zähler und Quoten der Belegdichte eines Berichts."""

    model_config = ConfigDict(extra="forbid")

    schema_version: int = 1
    #: Alle Claims der Evidence-Map.
    claims_total: int = Field(default=0, ge=0)
    #: Claims ohne Beleg mit ``supports_claim is True``.
    claims_without_support: int = Field(default=0, ge=0)
    #: Claims mit genau einem stützenden Beleg.
    claims_single_support: int = Field(default=0, ge=0)
    #: Claims mit zwei oder mehr stützenden Belegen.
    claims_multi_support: int = Field(default=0, ge=0)
    #: Claims mit zwei oder mehr *unabhängigen* stützenden Quellen (gleiche
    #: Regel wie der Confidence-Rechner: Belege einer Stimme zählen einmal).
    claims_multi_independent: int = Field(default=0, ge=0)
    #: Claims, deren ``confidence_score`` genau am Ein-Quellen-Deckel 0,59 liegt.
    claims_at_single_source_cap: int = Field(default=0, ge=0)
    #: Claims mit mindestens einem stützenden Beleg vom Typ ``agent_action``.
    claims_with_action_support: int = Field(default=0, ge=0)
    #: Stützende Verknüpfungen je Belegart (``unknown`` ohne bekannte Art).
    supporting_links_by_type: dict[str, int] = Field(default_factory=dict)
    #: Anteile an ``claims_total``; ``None``, wenn es keine Claims gibt.
    single_support_ratio: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    action_support_ratio: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    single_source_cap_ratio: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    multi_independent_ratio: Optional[float] = Field(default=None, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def _support_buckets_add_up(self) -> "EvidenceDensity":
        buckets = (
            self.claims_without_support
            + self.claims_single_support
            + self.claims_multi_support
        )
        if buckets != self.claims_total:
            raise ValueError(
                "claims_without_support + claims_single_support + "
                f"claims_multi_support ({buckets}) must equal claims_total "
                f"({self.claims_total})"
            )
        return self

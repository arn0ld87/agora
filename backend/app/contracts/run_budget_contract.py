"""
Run-Budget-Contract v1 (Pydantic v2, Issue #764).

Kanonischer, versionierter Vertrag für Kosten-, Token- und Zeitbudgets:
  - RunBudgetConfig: vom Nutzer gesetzte Limits (weich/hart)
  - BudgetWarning: auditierbare Warnung bei Limitüberschreitung
  - UsageMetrics: gemessener Verbrauch (Tokens, Kosten, Laufzeit, Aufrufe)
  - RunUsage: Verbrauch gesamt + pro Stage/Provider/Modell
  - RunBudgetStatus: Config + aktueller Verbrauch + Warnungen
  - PreflightEstimate: ehrlich gekennzeichnete Schätzung vor Run-Start

Regeln:
  - Geldbeträge ausschließlich als Integer-Micros (1 Einheit = 10^-6 Währung),
    niemals Floats.
  - Fehlende Providerdaten werden niemals als 0 ausgegeben: optionale Felder
    bleiben None, der Status kennzeichnet unknown/estimated/free/measured.
  - Lokale Modelle ohne Geldpreis: cost_status="free".
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

_STRICT = ConfigDict(extra="forbid")

BudgetDimension = Literal["tokens", "cost", "time", "calls"]
BudgetEnforcement = Literal["soft", "hard"]
CostStatus = Literal["measured", "estimated", "free", "unknown"]
TokensStatus = Literal["measured", "partial", "unknown"]
MeasurementStatus = Literal["complete", "partial", "unknown"]
DataQuality = Literal["high", "medium", "low", "unknown"]
BudgetState = Literal["ok", "warning", "exceeded"]

# Abbruchgründe auf Run-Ebene (Issue #764): Budgetabbruch muss von
# technischem Fehler und Nutzerabbruch unterscheidbar sein.
TerminationReason = Literal[
    "completed",
    "error",
    "user_cancel",
    "user_stop",
    "budget_tokens",
    "budget_cost",
    "budget_time",
    "budget_calls",
]


class RunBudgetConfig(BaseModel):
    """Vom Nutzer gesetzte Budget-Limits für einen Run.

    Alle Limits optional; None bedeutet „kein Limit". `enforcement` gilt
    für alle gesetzten Limits gemeinsam: soft = warnen und weiterlaufen,
    hard = weitere planbare Modellaufrufe deterministisch verhindern.
    """

    model_config = _STRICT

    schema_version: Literal[1] = 1
    max_tokens: Optional[int] = Field(None, ge=1)
    max_cost_micros: Optional[int] = Field(None, ge=1)
    max_duration_seconds: Optional[int] = Field(None, ge=1)
    max_llm_calls: Optional[int] = Field(None, ge=1)
    enforcement: BudgetEnforcement = "soft"
    currency: str = Field("USD", min_length=3, max_length=3)


class BudgetWarning(BaseModel):
    """Auditierbare Warnung bei (weicher oder harter) Limitüberschreitung."""

    model_config = _STRICT

    dimension: BudgetDimension
    severity: BudgetEnforcement
    threshold: int = Field(ge=0)
    observed: int = Field(ge=0)
    message: str = Field(min_length=1)
    ts: str = Field(min_length=1)  # ISO-8601 UTC


class UsageMetrics(BaseModel):
    """Gemessener Verbrauch eines Runs oder einer Teilmenge (Stage/Provider/Modell).

    Optionale Felder bleiben None, wenn die Datenquelle sie nicht liefert —
    der jeweilige Status macht die Datenqualität explizit.
    """

    model_config = _STRICT

    input_tokens: Optional[int] = Field(None, ge=0)
    output_tokens: Optional[int] = Field(None, ge=0)
    total_tokens: Optional[int] = Field(None, ge=0)
    llm_calls: int = Field(0, ge=0)
    cost_micros: Optional[int] = Field(None, ge=0)
    cost_status: CostStatus = "unknown"
    tokens_status: TokensStatus = "unknown"
    duration_ms: int = Field(0, ge=0)


class RunUsage(BaseModel):
    """Tatsächlicher Verbrauch eines Runs, aufgeschlüsselt nach Stage/Provider/Modell."""

    model_config = _STRICT

    schema_version: Literal[1] = 1
    totals: UsageMetrics
    by_stage: dict[str, UsageMetrics] = Field(default_factory=dict)
    by_provider: dict[str, UsageMetrics] = Field(default_factory=dict)
    by_model: dict[str, UsageMetrics] = Field(default_factory=dict)
    started_at: Optional[str] = None
    ended_at: Optional[str] = None
    measurement_status: MeasurementStatus = "unknown"
    # Version/Quelle der für Kosten verwendeten Providerpreise (Audit, #764)
    pricing_version: Optional[str] = None
    pricing_source: Optional[str] = None


class RunBudgetStatus(BaseModel):
    """Aktueller Budget-Zustand eines Runs: Config + Verbrauch + Warnungen."""

    model_config = _STRICT

    config: RunBudgetConfig
    consumed: UsageMetrics
    warnings: list[BudgetWarning] = Field(default_factory=list)
    status: BudgetState = "ok"
    exceeded_dimension: Optional[BudgetDimension] = None


class PreflightModelRef(BaseModel):
    """Ein für den Run aufgelöstes Modell samt Kostenklarheit."""

    model_config = _STRICT

    stage: str = Field(min_length=1)
    provider_id: str = Field(min_length=1)
    model_id: str = Field(min_length=1)
    base_url_sanitized: Optional[str] = None
    cost_status: CostStatus = "unknown"


class PreflightEstimate(BaseModel):
    """Ehrlich gekennzeichnete Schätzung vor dem Run-Start.

    Liefert Bereiche statt Pseudoexaktheit. Bei unzureichender Datenbasis
    bleiben die jeweiligen Felder None und data_quality/warnings erklären
    warum.
    """

    model_config = _STRICT

    schema_version: Literal[1] = 1
    is_estimate: Literal[True] = True
    estimated_tokens_low: Optional[int] = Field(None, ge=0)
    estimated_tokens_high: Optional[int] = Field(None, ge=0)
    estimated_cost_micros_low: Optional[int] = Field(None, ge=0)
    estimated_cost_micros_high: Optional[int] = Field(None, ge=0)
    estimated_duration_seconds_low: Optional[int] = Field(None, ge=0)
    estimated_duration_seconds_high: Optional[int] = Field(None, ge=0)
    cost_status: CostStatus = "unknown"
    models: list[PreflightModelRef] = Field(default_factory=list)
    pricing_version: str = Field(min_length=1)
    pricing_source: str = Field(min_length=1)
    data_quality: DataQuality = "unknown"
    warnings: list[str] = Field(default_factory=list)

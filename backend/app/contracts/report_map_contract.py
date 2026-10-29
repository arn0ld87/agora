"""Evidence-Map und Export-Verträge für Report-Contract v2 (Pydantic v2).

Enthält EvidenceMapModel, EvidenceOmissionModel, Response-Varianten und
ReportContractModel samt zugehörigen Validatoren.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Mapping, Optional, Sequence, Union

from pydantic import (
    BaseModel,
    Field,
    GetJsonSchemaHandler,
    RootModel,
    model_validator,
)
from pydantic.json_schema import JsonSchemaValue
from pydantic_core import CoreSchema

from .report_claim_contract import (
    EvidenceCoverageEntry,
    EvidenceDegradationModel,
    IndexedReportClaimModel,
    _reject_dangling_ledger_refs,
    _role_family_key,
)
from .report_evidence_contract import (
    _STRICT,
    ClaimEvidenceBindingModel,
    ConfidenceLabel,
    EvidenceRecordModel,
    EvidenceSourceKind,
    counts_for_confidence,
    has_two_action_voices,
)
from .report_section_contract import (
    ReportModel,
    ReportSectionModel,
)


def _reject_mismatched_index_keys(index: Mapping[str, EvidenceRecordModel]) -> None:
    """Der Schluessel des ``evidence_index`` IST die kanonische Evidence-ID.

    Zwei Schreibweisen derselben Evidence wuerden beim Roundtrip still
    auseinanderlaufen: die eine Stelle loest ueber den Key auf, die andere
    ueber das Feld.
    """
    mismatched = sorted(key for key, record in index.items() if key != record.evidence_id)
    if mismatched:
        raise ValueError(
            "evidence_index-Key stimmt nicht mit evidence_id ueberein: " + ", ".join(mismatched)
        )


def _reject_unknown_global_refs(refs: Sequence[str], known_ids: set[str]) -> None:
    unknown = sorted(set(refs) - known_ids)
    if unknown:
        raise ValueError(
            "global_evidence_refs enthalten unbekannte Evidence: " + ", ".join(unknown)
        )


def _validate_claim_bindings(
    section: ReportSectionModel,
    claim: IndexedReportClaimModel,
    known_ids: set[str],
    index: Mapping[str, EvidenceRecordModel],
) -> None:
    """Alle Regeln, die an einem Claim haengen, in dieser Reihenfolge.

    Die Reihenfolge ist Teil des Verhaltens: die medium-Regel und die
    Stakeholder-Regel melden vor der ADR-0022-Begruendung, weil ihre
    Bedingungen breiter greifen. Eine Umstellung macht Fehlermeldungen
    ununterscheidbar.
    """
    unknown = sorted({binding.evidence_id for binding in claim.evidence} - known_ids)
    if unknown:
        raise ValueError(
            f"Section {section.section_index} Claim {claim.claim_id} "
            "referenziert unbekannte Evidence: " + ", ".join(unknown)
        )

    resolved = [(binding, index[binding.evidence_id]) for binding in claim.evidence]
    if claim.confidence_label in (ConfidenceLabel.high, ConfidenceLabel.verified):
        _require_two_supporting_groups(section, claim, resolved)
        _reject_inferred_evidence(section, claim, resolved)
    elif claim.confidence_label == ConfidenceLabel.medium:
        _require_quote_and_seed(section, claim, resolved)
    _reject_label_resting_on_hand_work(section, claim, resolved)


def _require_two_supporting_groups(
    section: ReportSectionModel,
    claim: IndexedReportClaimModel,
    resolved: Sequence[tuple[ClaimEvidenceBindingModel, EvidenceRecordModel]],
) -> None:
    """ADR-0002 Anker 4: zwei *stuetzende* Rollenfamilien, nicht zwei Zitate.

    Issue #1248 Folgefehler (Review B7): dieser Validator zaehlte bisher den
    rohen ``persona_stakeholder_group``-Wert, waehrend Schreibpfad
    (``auto_downgrade_unsupported_high_claims``) und der Hartanker
    ``cross_stakeholder_for_high`` ueber ``_role_family_key`` normalisieren.
    Persistierte Altbestaende umgehen den Schreibpfad, sodass "Buerger" und
    "buerger " hier als zwei Gruppen zaehlten, obwohl sie eine Rolle sind.
    Verschaerfung von ADR-0002 Anker 4, keine Schwaechung: die Zahl
    unterscheidbarer Gruppen kann dadurch nur sinken.
    """
    groups = {
        _role_family_key(record)
        for binding, record in resolved
        if binding.supports_claim
        and record.source_kind == EvidenceSourceKind.agent_quote
        and record.persona_stakeholder_group
        and counts_for_confidence(record)
    }
    if len(groups) < 2:
        raise ValueError(
            f"Section {section.section_index} Claim {claim.claim_id}: "
            "high/verified verlangt zwei stuetzende Stakeholder-Gruppen."
        )


def _reject_inferred_evidence(
    section: ReportSectionModel,
    claim: IndexedReportClaimModel,
    resolved: Sequence[tuple[ClaimEvidenceBindingModel, EvidenceRecordModel]],
) -> None:
    if any(record.source_kind == EvidenceSourceKind.inferred for _, record in resolved):
        raise ValueError(
            f"Section {section.section_index} Claim {claim.claim_id}: "
            "inferred Evidence ist fuer high/verified unzulaessig."
        )


def _require_quote_and_seed(
    section: ReportSectionModel,
    claim: IndexedReportClaimModel,
    resolved: Sequence[tuple[ClaimEvidenceBindingModel, EvidenceRecordModel]],
) -> None:
    """``medium`` verlangt eine simulierte Stimme *und* einen Dokumentfakt.

    Nur ``source_kind`` reicht beim Zitat nicht: ohne ``quote``-Feld traegt der
    Record keinen Wortlaut, den eine Persona tatsaechlich geaussert haette.

    ADR-0002-Nachtrag 2026-10-10 (#1778): alternativ genuegen stuetzende
    ``agent_action``-Belege von mind. zwei verschiedenen Stimmen (``voice_key``
    am Record, ``supports_claim`` am Binding).
    """
    has_agent_quote = any(
        record.source_kind == EvidenceSourceKind.agent_quote
        and bool(record.quote)
        and binding.supports_claim is True
        and counts_for_confidence(record)
        for binding, record in resolved
    )
    has_seed = any(
        record.source_kind == EvidenceSourceKind.seed_corpus
        and binding.supports_claim is True
        and counts_for_confidence(record)
        for binding, record in resolved
    )
    has_action_voices = has_two_action_voices(
        (record.source_kind, record.voice_key)
        for binding, record in resolved
        if binding.supports_claim is True and counts_for_confidence(record)
    )
    if not ((has_agent_quote and has_seed) or has_action_voices):
        raise ValueError(
            f"Section {section.section_index} Claim {claim.claim_id}: "
            "medium verlangt agent_quote und seed_corpus oder stuetzende "
            "agent_action-Belege von mindestens zwei verschiedenen Stimmen."
        )


def _reject_label_resting_on_hand_work(
    section: ReportSectionModel,
    claim: IndexedReportClaimModel,
    resolved: Sequence[tuple[ClaimEvidenceBindingModel, EvidenceRecordModel]],
) -> None:
    """ADR-0022 §4 (#1808): Handarbeit im Graphen zaehlt fuer keine Stufe.

    Die Kompositionsregeln fragen ausschliesslich nach ``agent_quote`` /
    ``seed_corpus`` — beides kann ein Record mit ``graph_origin`` nicht sein
    (``graph_origin_is_never_a_document_fact``). Offen bleiben die
    Binding-Regeln aus ``IndexedReportClaimModel``, die den Record nicht
    kennen: sie muessen auch ohne die Handarbeit halten. Diese zusaetzliche
    Pruefung laesst die bestehenden unveraendert; ohne ``graph_origin`` im
    Index greift sie nie.

    ``speculative``/``low`` bleiben ausgenommen: dort ist die Handevidence
    sichtbar, aber nie labelerhebend.
    """
    if claim.confidence_label in (ConfidenceLabel.speculative, ConfidenceLabel.low):
        return
    counted = [binding for binding, record in resolved if counts_for_confidence(record)]
    if len(counted) == len(resolved):
        return
    reason = _hand_work_reason(claim, counted)
    if reason is not None:
        raise ValueError(
            f"Section {section.section_index} Claim {claim.claim_id}: "
            f"Label '{claim.confidence_label.value}' wird nur mit "
            "manueller oder bearbeiteter Graph-Evidence erreicht "
            f"({reason}); sie zaehlt fuer keine Confidence-Stufe "
            "(ADR-0022)."
        )


def _hand_work_reason(
    claim: IndexedReportClaimModel,
    counted: Sequence[ClaimEvidenceBindingModel],
) -> Optional[str]:
    """Welche Binding-Schwelle erreicht nur die Handevidence — oder keine."""
    if not counted:
        return "ausschliesslich solche Evidence gebunden"
    if claim.confidence_label in (
        ConfidenceLabel.high,
        ConfidenceLabel.verified,
    ) and not any(binding.supports_claim for binding in counted):
        return "supports_claim=True nur an solcher Evidence"
    if claim.confidence_label == ConfidenceLabel.verified:
        if not any((binding.match_score or 0.0) >= 0.85 for binding in counted):
            return "match_score >= 0.85 nur an solcher Evidence"
        supporting_counted = [b for b in counted if b.supports_claim]
        if len({b.evidence_id for b in supporting_counted}) < 2:
            return "mindestens zwei stuetzende Quellen nur mit solcher Evidence"
    return None


class EvidenceMapModel(BaseModel):
    """Persistierte Evidence-Map. Ablöse für die rohen Dicts in report_agent.py."""

    model_config = _STRICT
    schema_version: Literal[3] = 3
    report_id: str = Field(min_length=1)
    simulation_id: str = Field(min_length=1)
    evidence_index: dict[str, EvidenceRecordModel] = Field(default_factory=dict)
    global_evidence_refs: list[str] = Field(default_factory=list)
    sections: list[ReportSectionModel] = Field(default_factory=list)
    # Issue #1006: additiv, Default leer — bestehende persistierte
    # EvidenceMaps ohne dieses Feld validieren unverändert weiter.
    degradation_log: list[EvidenceDegradationModel] = Field(default_factory=list)
    #: Audit-Trail regulärer Evidence-Gate-Entscheidungen (fehlende Evidence,
    #: fehlende Supporting-Evidence, Fließtext-Entfernungen). Bewusst getrennt
    #: vom ``degradation_log``: der dokumentiert Validator-Reparaturen und
    #: stuft den Report-Status über ``apply_degradation_downgrade`` auf
    #: INCOMPLETE ab — ein erwartetes Hypothesen-Routing im Balanced-Modus
    #: ist dagegen kein Statusmangel (Codex-Review PR #1151, P1).
    gate_decision_log: list[EvidenceDegradationModel] = Field(default_factory=list)
    #: Verbleib jedes quantitativen Tool-Fakts auf dem Weg in den
    #: ``evidence_index``. Additiv, Default leer — bestehende persistierte
    #: EvidenceMaps ohne dieses Feld validieren unverändert weiter (dieselbe
    #: Linie wie ``degradation_log``, Issue #1006).
    evidence_coverage_ledger: list[EvidenceCoverageEntry] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_evidence_cross_references(self) -> "EvidenceMapModel":
        known_ids = set(self.evidence_index)
        _reject_mismatched_index_keys(self.evidence_index)
        _reject_dangling_ledger_refs(self.evidence_coverage_ledger, known_ids)
        _reject_unknown_global_refs(self.global_evidence_refs, known_ids)
        for section in self.sections:
            for claim in section.claims:
                _validate_claim_bindings(section, claim, known_ids, self.evidence_index)
        return self


class EvidenceOmissionModel(BaseModel):
    """Warum ein Export-Envelope keine Evidence-Map traegt (Issue #987).

    Bis #987 fiel eine Evidence-Map, die nach allen Migrationen den Vertrag
    verletzte, mit einer ``logger.warning`` aus dem Envelope. Der Nutzer bekam
    HTTP 200 und eine herunterladbare JSON-Datei mit ``evidence: null`` — von
    einem Report ohne Evidence nicht zu unterscheiden.

    Der Fallback bleibt: ein unvollstaendiger Export ist besser als gar keiner,
    und der Report-Rumpf ist unbeschaedigt. Er ist nur nicht laenger stumm.

    Abgrenzung zu ``EvidenceDegradationModel`` (#1006): das protokolliert die
    Abstufung eines *einzelnen Claims* waehrend der Report-Erzeugung. Hier ist
    die *gesamte Map* nicht ausliefertbar, und zwar erst beim Export.
    """

    model_config = _STRICT
    reason: Literal["contract_violation"] = Field(
        description=(
            "Stabiler Schluessel. Die Oberflaeche uebersetzt daraus per "
            "vue-i18n — dieser Vertrag transportiert keinen UI-Text."
        ),
    )
    detail: str = Field(
        min_length=1,
        description=(
            "Erklaerung fuer den Leser der exportierten Datei, nicht fuer die "
            "Oberflaeche: wer die JSON spaeter ohne Agora oeffnet, soll den "
            "fehlenden Evidence-Teil einordnen koennen."
        ),
    )
    validation_errors: list[str] = Field(
        default_factory=list,
        max_length=5,
        description=(
            "Die ersten Validierungsfehler als ``loc: msg``. Belegt die "
            "Einstufung, ohne die verworfenen Rohdaten mitzuexportieren."
        ),
    )


class EvidenceMapResponseSuccessVariant(BaseModel):
    """Erfolgsvariante von ``EvidenceMapResponseModel`` (Issue #1477 F3)."""

    model_config = _STRICT
    success: Literal[True] = Field(
        description=(
            "Pflichtfeld ohne Default (Review B7 Runde 5, Issue #1477 F1): "
            "ein Default wandert im generierten JSON-Schema aus der "
            '``required``-Liste heraus und liesse ``{"data": ...}`` ohne '
            "``success`` durch, obwohl die Zod-Grenze im Frontend "
            "(``reportContract.ts``) ``success: true`` verlangt."
        ),
    )
    data: EvidenceMapModel


class EvidenceMapResponseOmittedVariant(BaseModel):
    """Degradations-Variante von ``EvidenceMapResponseModel`` (Issue #1477 F3)."""

    model_config = _STRICT
    success: Literal[True] = Field(
        description=(
            "Pflichtfeld ohne Default (Review B7 Runde 5, Issue #1477 F1) — "
            "siehe ``EvidenceMapResponseSuccessVariant.success``."
        ),
    )
    evidence_omitted: EvidenceOmissionModel


class EvidenceMapResponseModel(
    RootModel[Union[EvidenceMapResponseSuccessVariant, EvidenceMapResponseOmittedVariant]]
):
    """Response-Envelope fuer ``GET /api/report/<id>/evidence`` (Review B7 Fix, Issue #1477 F1/F3)."""

    root: Union[EvidenceMapResponseSuccessVariant, EvidenceMapResponseOmittedVariant]

    @classmethod
    def for_data(cls, data: EvidenceMapModel) -> "EvidenceMapResponseModel":
        return cls(root=EvidenceMapResponseSuccessVariant(success=True, data=data))

    @classmethod
    def for_omission(cls, evidence_omitted: EvidenceOmissionModel) -> "EvidenceMapResponseModel":
        return cls(
            root=EvidenceMapResponseOmittedVariant(success=True, evidence_omitted=evidence_omitted)
        )

    @classmethod
    def __get_pydantic_json_schema__(
        cls, core_schema: CoreSchema, handler: GetJsonSchemaHandler
    ) -> JsonSchemaValue:
        schema = handler(core_schema)
        if "anyOf" in schema:
            schema["oneOf"] = schema.pop("anyOf")
        return schema

    def to_payload(self) -> dict[str, Any]:
        return self.root.model_dump(mode="json")


class ReportContractModel(BaseModel):
    """Wurzel — was tatsächlich beim Export rausgeht."""

    model_config = _STRICT
    schema_version: Literal[2] = 2
    exported_at: datetime
    report: ReportModel
    evidence: Optional[EvidenceMapModel] = None
    # Issue #987: additiv, Default None. Gesetzt genau dann, wenn eine
    # Evidence-Map vorlag, aber nicht ausgeliefert werden konnte. Ein Report
    # ohne Evidence-Artefakt laesst das Feld None — kein Hinweis ohne Anlass.
    evidence_omitted: Optional[EvidenceOmissionModel] = None


__all__ = [
    "EvidenceMapModel",
    "EvidenceOmissionModel",
    "EvidenceMapResponseSuccessVariant",
    "EvidenceMapResponseOmittedVariant",
    "EvidenceMapResponseModel",
    "ReportContractModel",
    "_reject_mismatched_index_keys",
    "_reject_unknown_global_refs",
    "_validate_claim_bindings",
    "_require_two_supporting_groups",
    "_reject_inferred_evidence",
    "_require_quote_and_seed",
    "_reject_label_resting_on_hand_work",
    "_hand_work_reason",
]

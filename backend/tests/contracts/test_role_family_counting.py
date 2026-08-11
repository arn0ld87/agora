"""Issue #1248 — ``cross_stakeholder_for_high`` zählt Freitext-Jobtitel.

``persona_stakeholder_group`` wird aus dem Berufstitel der Persona gefüllt und
ist damit ein frei formulierter Satz. Der Validator zählt distinkte Werte nach
einer Normalisierung, die nur Groß-/Kleinschreibung und Whitespace einebnet.

Gemessen an den Evidence-Karten zweier Referenzläufe:

    40 agent_quotes, 16 "distinkte" Gruppen:
       4x  Umschüler im IT-Bereich (Teilnehmer)
       2x  Teilnehmer einer IT-Umschulung (Retrainee)     ← identische Rolle

    33 agent_quotes, 15 "distinkte" Gruppen:
       2x  Umschüler & Sprecher der Teilnehmenden
       1x  Umschüler zur Fachkraft für Lagerlogistik
       1x  Umschüler:in (Logistik & Lagerwesen)           ← eine Rolle
       1x  Umschülerin zur Kauffrau für E-Commerce

In einem weiteren Lauf genügte ein Genusunterschied: ``Festangestellte
Dozentin für IT-Umschulungen und Betriebsratsmitglied`` gegen
``Festangestellter Fachdozent für IT-Umschulungen und Betriebsratsmitglied``.

Der Anker verlangt zwei distinkte Gruppen für ``high``. Es genügte also eine
andere Formulierung desselben Berufs, um eine Aussage als breit gestützt
einzustufen, obwohl nur eine Perspektive gesprochen hat.

**Verhältnis zu ADR-0002:** Dieses Issue *stärkt* Hartanker 4. Der Validator
bleibt in Kraft und wird strenger — die Zahl unterscheidbarer Gruppen kann
durch das Label nur sinken.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.contracts.report_contract import (
    ConfidenceLabel,
    EvidenceSourceKind,
    EvidenceType,
    ReportClaimModel,
)


def _quote(
    idx: int,
    *,
    job_title: str,
    role_family: str | None = None,
) -> dict:
    """Ein stützendes ``agent_quote``-Evidence-Item."""
    item = {
        "type": EvidenceType.agent_interview.value,
        "source": f"interview-{idx}",
        "snippet": f"Aussage {idx} aus dem Interview.",
        "quote": f"Zitat {idx}",
        "source_kind": EvidenceSourceKind.agent_quote.value,
        "supports_claim": True,
        "persona_stakeholder_group": job_title,
    }
    if role_family is not None:
        item["persona_role_family"] = role_family
    return item


def _claim(evidence: list[dict], label: ConfidenceLabel = ConfidenceLabel.high) -> dict:
    return {
        "claim_id": "claim_01",
        "claim_text": "Die Umschulung braucht verbindliche Absprachen.",
        "confidence_label": label,
        "confidence_score": 0.9 if label == ConfidenceLabel.high else 0.3,
        "evidence": evidence,
    }


class TestRollenfamilieStattJobtitel:
    def test_wortwahlvarianten_derselben_rolle_sind_eine_gruppe(self):
        """RED ohne den Fix: zwei Jobtitel, zwei Gruppen, `high` geht durch."""
        evidence = [
            _quote(1, job_title="Umschüler im IT-Bereich (Teilnehmer)", role_family="Retrainee"),
            _quote(2, job_title="Teilnehmer einer IT-Umschulung (Retrainee)", role_family="Retrainee"),
        ]

        with pytest.raises(ValidationError) as excinfo:
            ReportClaimModel.model_validate(_claim(evidence))

        assert "Rollenfamilien" in str(excinfo.value)

    def test_genusunterschied_ist_keine_zweite_gruppe(self):
        """Der beobachtete Minimalfall: dieselbe Rolle, anderes Genus."""
        evidence = [
            _quote(
                1,
                job_title="Festangestellte Dozentin für IT-Umschulungen und Betriebsratsmitglied",
                role_family="PermanentLecturer",
            ),
            _quote(
                2,
                job_title="Festangestellter Fachdozent für IT-Umschulungen und Betriebsratsmitglied",
                role_family="PermanentLecturer",
            ),
        ]

        with pytest.raises(ValidationError):
            ReportClaimModel.model_validate(_claim(evidence))

    def test_vier_formulierungen_einer_rolle_bleiben_eine_gruppe(self):
        """Der zweite Referenzlauf: vier "Gruppen", eine Rolle."""
        evidence = [
            _quote(1, job_title="Umschüler & Sprecher der Teilnehmenden", role_family="Retrainee"),
            _quote(2, job_title="Umschüler zur Fachkraft für Lagerlogistik", role_family="Retrainee"),
            _quote(3, job_title="Umschüler:in (Logistik & Lagerwesen)", role_family="Retrainee"),
            _quote(4, job_title="Umschülerin zur Kauffrau für E-Commerce", role_family="Retrainee"),
        ]

        with pytest.raises(ValidationError):
            ReportClaimModel.model_validate(_claim(evidence))

    def test_echte_rollenvielfalt_traegt_high_weiterhin(self):
        """Gegenprobe: zwei wirklich verschiedene Familien bleiben zwei Gruppen."""
        evidence = [
            _quote(1, job_title="Umschüler im IT-Bereich", role_family="Retrainee"),
            _quote(2, job_title="Betriebsrätin", role_family="WorksCouncilMember"),
        ]

        claim = ReportClaimModel.model_validate(_claim(evidence))
        assert claim.confidence_label == ConfidenceLabel.high

    def test_jobtitel_bleibt_als_anzeigetext_erhalten(self):
        """Der Titel trägt Information, die der Report nutzt — er verschwindet nicht."""
        evidence = [
            _quote(1, job_title="Umschüler im IT-Bereich", role_family="Retrainee"),
            _quote(2, job_title="Betriebsrätin", role_family="WorksCouncilMember"),
        ]

        claim = ReportClaimModel.model_validate(_claim(evidence))
        titles = [e.persona_stakeholder_group for e in claim.evidence]
        assert titles == ["Umschüler im IT-Bereich", "Betriebsrätin"]


class TestKollektivUndIndividuum:
    def test_kollektiv_und_individuum_derselben_organisation_sind_eine_familie(self):
        """Ein Kollektiv-Zitat ist keine zusätzliche Stimme neben einem Individuum.

        Beide tragen den Entitätstyp ihrer Quellentität als Rollenfamilie —
        die Zusammenführung fällt damit automatisch an, ohne eine zweite
        Identitätsquelle.
        """
        evidence = [
            _quote(1, job_title="Agentur für Arbeit", role_family="FundingAgency"),
            _quote(2, job_title="Sachbearbeiterin im Jobcenter", role_family="FundingAgency"),
        ]

        with pytest.raises(ValidationError):
            ReportClaimModel.model_validate(_claim(evidence))


class TestRueckwaertskompatibilitaet:
    def test_ohne_label_bleibt_das_bisherige_verhalten(self):
        """Artefakte aus Läufen vor diesem Slice tragen kein Label.

        Dort bleibt der Jobtitel die Vergleichsgröße — nie strenger als
        vorher, aber auch nie lockerer.
        """
        evidence = [
            _quote(1, job_title="Umschüler im IT-Bereich"),
            _quote(2, job_title="Betriebsrätin"),
        ]

        claim = ReportClaimModel.model_validate(_claim(evidence))
        assert claim.confidence_label == ConfidenceLabel.high

    def test_gemischt_label_und_kein_label_kollidieren_nicht(self):
        """Ein Label ``Lecturer`` darf nicht mit dem Jobtitel ``Lecturer`` verschmelzen.

        Die beiden Namensräume werden über ein Präfix getrennt; ohne das wäre
        eine Familie von einem gleichlautenden Freitext nicht zu unterscheiden.
        """
        evidence = [
            _quote(1, job_title="Lecturer", role_family="Lecturer"),
            _quote(2, job_title="Lecturer"),
        ]

        claim = ReportClaimModel.model_validate(_claim(evidence))
        assert claim.confidence_label == ConfidenceLabel.high

    def test_niedrige_labels_bleiben_unberuehrt(self):
        """Der Anker greift nur für high/verified."""
        evidence = [
            _quote(1, job_title="Umschüler", role_family="Retrainee"),
            _quote(2, job_title="Teilnehmer", role_family="Retrainee"),
        ]

        claim = ReportClaimModel.model_validate(
            _claim(evidence, label=ConfidenceLabel.low)
        )
        assert claim.confidence_label == ConfidenceLabel.low


class TestZaehlerImAgentPfad:
    def test_evidence_zaehler_folgt_derselben_regel(self):
        """``count_distinct_stakeholder_groups`` muss dasselbe zählen wie der Validator."""
        from app.services.report_agent.evidence import (
            _count_supporting_stakeholder_groups as count_groups,
        )

        same_role = [
            {
                "source_kind": "agent_quote",
                "supports_claim": True,
                "persona_stakeholder_group": "Umschüler im IT-Bereich",
                "persona_role_family": "Retrainee",
            },
            {
                "source_kind": "agent_quote",
                "supports_claim": True,
                "persona_stakeholder_group": "Teilnehmer einer IT-Umschulung",
                "persona_role_family": "Retrainee",
            },
        ]
        assert count_groups(same_role) == 1

        two_roles = [
            same_role[0],
            {
                "source_kind": "agent_quote",
                "supports_claim": True,
                "persona_stakeholder_group": "Betriebsrätin",
                "persona_role_family": "WorksCouncilMember",
            },
        ]
        assert count_groups(two_roles) == 2

    def test_konsenswert_folgt_derselben_regel(self):
        """Der Confidence-Konsens darf keine andere Vorstellung von "Gruppe" haben."""
        from app.services.confidence_calculator import compute_confidence_breakdown

        same_role = [
            {
                "type": "agent_interview",
                "source_kind": "agent_quote",
                "supports_claim": True,
                "quote": "A",
                "persona_stakeholder_group": "Umschüler im IT-Bereich",
                "persona_role_family": "Retrainee",
            },
            {
                "type": "agent_interview",
                "source_kind": "agent_quote",
                "supports_claim": True,
                "quote": "B",
                "persona_stakeholder_group": "Teilnehmer einer IT-Umschulung",
                "persona_role_family": "Retrainee",
            },
        ]
        two_roles = [
            same_role[0],
            {**same_role[1], "persona_role_family": "WorksCouncilMember"},
        ]

        same = compute_confidence_breakdown(same_role)
        two = compute_confidence_breakdown(two_roles)

        assert same["stakeholder_group_count"] == 1.0, (
            "Zwei Formulierungen derselben Rolle sind eine Gruppe, "
            f"gezählt wurden {same['stakeholder_group_count']}"
        )
        assert two["stakeholder_group_count"] == 2.0
        assert two["simulation_consensus"] > same["simulation_consensus"]


class TestVertragUndSchema:
    def test_feld_ist_optional_und_laengenbegrenzt(self):
        from app.contracts.report_contract import EvidenceItemModel

        field = EvidenceItemModel.model_fields["persona_role_family"]
        assert field.default is None
        assert any(getattr(m, "max_length", None) == 120 for m in field.metadata)

    def test_record_und_item_tragen_dasselbe_feld(self):
        from app.contracts.report_contract import (
            EvidenceItemModel,
            EvidenceRecordModel,
        )

        assert "persona_role_family" in EvidenceItemModel.model_fields
        assert "persona_role_family" in EvidenceRecordModel.model_fields

    def test_migration_traegt_das_feld_mit(self):
        """Ohne den Eintrag fiele das Label beim Migrieren still weg."""
        from app.services.evidence_migrations import _RECORD_FIELDS

        assert "persona_role_family" in _RECORD_FIELDS


class TestAuffangtypenSindKeineRollenfamilie:
    """CodeRabbit PR #1260: `Person` und `Organization` sind Fallback-Töpfe.

    Die Ontologie führt sie bewusst als breite Auffangtypen. Sie als
    Rollenfamilie zu zählen würde zwei völlig verschiedene Stakeholder — etwa
    einen Bildungsträger und eine Aufsichtsbehörde, beide `Organization` —
    zu einer Stimme verschmelzen und Cross-Stakeholder-Stützung unmöglich
    machen. Für sie bleibt der Berufstitel die Vergleichsgröße.
    """

    def test_zwei_organisationen_bleiben_zwei_gruppen(self):
        evidence = [
            _quote(1, job_title="Nordharz Bildungswerk gGmbH", role_family="Organization"),
            _quote(2, job_title="Agentur für Arbeit", role_family="Organization"),
        ]

        claim = ReportClaimModel.model_validate(_claim(evidence))
        assert claim.confidence_label == ConfidenceLabel.high

    def test_zwei_personen_bleiben_zwei_gruppen(self):
        evidence = [
            _quote(1, job_title="Dozentin", role_family="Person"),
            _quote(2, job_title="Betriebsrätin", role_family="Person"),
        ]

        claim = ReportClaimModel.model_validate(_claim(evidence))
        assert claim.confidence_label == ConfidenceLabel.high

    def test_gleicher_jobtitel_unter_auffangtyp_bleibt_eine_gruppe(self):
        """Die Whitespace-Normalisierung aus #1160 C greift weiterhin."""
        evidence = [
            _quote(1, job_title="Umschüler", role_family="Organization"),
            _quote(2, job_title="  umschüler ", role_family="Organization"),
        ]

        with pytest.raises(ValidationError):
            ReportClaimModel.model_validate(_claim(evidence))

    def test_spezifische_familie_wirkt_weiterhin(self):
        """Gegenprobe: ein echtes Rollenlabel kollabiert wie vorgesehen."""
        evidence = [
            _quote(1, job_title="Umschüler im IT-Bereich", role_family="Retrainee"),
            _quote(2, job_title="Teilnehmer einer Umschulung", role_family="Retrainee"),
        ]

        with pytest.raises(ValidationError):
            ReportClaimModel.model_validate(_claim(evidence))

    def test_beide_zaehler_teilen_die_ausnahme(self):
        from app.services.confidence_calculator import compute_confidence_breakdown
        from app.services.report_agent.evidence import (
            _count_supporting_stakeholder_groups as count_groups,
        )

        items = [
            {
                "type": "agent_interview",
                "source_kind": "agent_quote",
                "supports_claim": True,
                "quote": "A",
                "persona_stakeholder_group": "Bildungsträger",
                "persona_role_family": "Organization",
            },
            {
                "type": "agent_interview",
                "source_kind": "agent_quote",
                "supports_claim": True,
                "quote": "B",
                "persona_stakeholder_group": "Aufsichtsbehörde",
                "persona_role_family": "Organization",
            },
        ]

        assert count_groups(items) == 2
        assert compute_confidence_breakdown(items)["stakeholder_group_count"] == 2.0

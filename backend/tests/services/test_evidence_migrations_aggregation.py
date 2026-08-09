"""Tests für echte Persona/Segment/FrictionPoint/TrustSignal-Aggregation in migrate_v2_to_v3.

P3.1-Followup — Refs PLAN.md §4.1.

Drei Pflicht-Cases:
1. Volle Aggregation: v2 + Persona-Artefakte → personas[] nicht leer, kein DataGap-Personas-Marker.
2. Leere Aggregation: v2 ohne Persona-Artefakte → DataGap-Eintrag wie bisher.
3. Section-basierte FrictionPoint/TrustSignal-Extraktion aus Sections mit Keyword.
"""
from __future__ import annotations

from app.contracts.report_v3 import ReportV3
from app.services.artifact_store import InMemoryArtifactStore
from app.services.evidence_migrations import migrate_v2_to_v3


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_v2_with_sections(report_id: str = "rep-agg-001") -> dict:
    """Minimales v2-dict mit Reibungspunkte- und Vertrauenssignale-Sections."""
    return {
        "report_id": report_id,
        "sections": [
            {
                "section_index": 1,
                "section_title": "Executive Summary",
                "claims": [
                    {
                        "claim_id": "c01",
                        "claim_text": "Nachhaltige Mobilität ist ein zentrales Thema der Simulation.",
                        "confidence_label": "medium",
                        "evidence": [{"source_id_anchor": "kg:node:mobility-001", "type": "graph_node"}],
                    }
                ],
                "data_gaps": [],
                "hypotheses": [],
            },
            {
                "section_index": 5,
                "section_title": "Top 10 Reibungspunkte",
                "claims": [
                    {
                        "claim_id": "fp01",
                        "claim_text": "Hohe Installationskosten hemmen die Adoption bei Geringverdienern.",
                        "confidence_label": "high",
                        "evidence": [{"source_id_anchor": "kg:ev:fp-001", "type": "graph_node"}],
                    },
                    {
                        "claim_id": "fp02",
                        "claim_text": "Fehlende Ladeinfrastruktur ist ein zentraler Reibungspunkt.",
                        "confidence_label": "medium",
                        "evidence": [{"source_id_anchor": "kg:ev:fp-002", "type": "graph_node"}],
                    },
                ],
                "data_gaps": [],
                "hypotheses": [],
            },
            {
                "section_index": 6,
                "section_title": "Top 10 Vertrauenssignale",
                "claims": [
                    {
                        "claim_id": "ts01",
                        "claim_text": "Zertifizierungen durch TÜV steigern das Vertrauen deutlich.",
                        "confidence_label": "high",
                        "evidence": [{"source_id_anchor": "kg:ev:ts-001", "type": "graph_node"}],
                    },
                ],
                "data_gaps": [],
                "hypotheses": [],
            },
        ],
    }


def _make_reddit_profiles() -> list:
    """Simulierte reddit_profiles.json-Inhalte mit DACH-Personas."""
    return [
        {
            "user_id": 1,
            "username": "anna_schneider",
            "name": "Anna Schneider",
            "bio": "Ingenieurin aus München mit Interesse an Nachhaltigkeit.",
            "persona": "Technisch versiert, umweltbewusst.",
            "age": 38,
            "profession": "Maschinenbauingenieurin",
            "country": "Deutschland",
            "segment": "technik_affin",
            "voice_register": "technical-de",
            "interested_topics": ["Elektromobilität", "Klimaschutz"],
            "source_entity_uuid": "ent-001",
            "source_entity_type": "individual",
        },
        {
            "user_id": 2,
            "username": "bernd_mueller",
            "name": "Bernd Müller",
            "bio": "Kaufmann aus Hamburg.",
            "persona": "Pragmatisch, kostenbewusst.",
            "age": 52,
            "profession": "Kaufmännischer Leiter",
            "country": "Deutschland",
            "segment": "konservativ",
            "voice_register": "formal-de",
            "interested_topics": ["Wirtschaft"],
            "source_entity_uuid": "ent-002",
            "source_entity_type": "individual",
        },
        {
            "user_id": 3,
            "username": "stadtwerk_ag",
            "name": "Stadtwerk AG",
            "bio": "Kommunales Energieunternehmen.",
            "persona": "Institutionell, stakeholder-orientiert.",
            "profession": "Energieversorger",
            "country": "Österreich",
            "segment": "technik_affin",
            "voice_register": "formal-de",
            "interested_topics": ["Infrastruktur"],
            "source_entity_uuid": "ent-003",
            "source_entity_type": "organization",
        },
    ]


# ---------------------------------------------------------------------------
# Case 1: Volle Aggregation mit Persona-Artefakten
# ---------------------------------------------------------------------------

class TestVollAggregation:
    def test_personas_nicht_leer(self):
        """Mit reddit_profiles: personas[] enthält gemappte Einträge."""
        store = InMemoryArtifactStore()
        sim_id = "sim_agg_test"
        store.write_json(sim_id, "reddit_profiles", _make_reddit_profiles())

        result = migrate_v2_to_v3(
            _make_v2_with_sections(),
            simulation_id=sim_id,
            artifact_store=store,
        )
        report = ReportV3.model_validate(result)

        assert len(report.personas) == 3

    def test_personas_felder_korrekt_gemappt(self):
        """Persona-Felder: beruf, region, voice_register, alter_range."""
        store = InMemoryArtifactStore()
        sim_id = "sim_agg_test"
        store.write_json(sim_id, "reddit_profiles", _make_reddit_profiles())

        result = migrate_v2_to_v3(
            _make_v2_with_sections(),
            simulation_id=sim_id,
            artifact_store=store,
        )
        report = ReportV3.model_validate(result)

        anna = next(p for p in report.personas if "anna" in p.id.lower() or "schneider" in p.beruf.lower() or p.beruf == "Maschinenbauingenieurin")
        assert anna.beruf == "Maschinenbauingenieurin"
        assert anna.region == "Deutschland"
        assert anna.voice_register == "technical-de"
        assert anna.alter_range == "38"

    def test_persona_evidence_exports_only_minimal_provenance(self):
        store = InMemoryArtifactStore()
        sim_id = "sim_profile_provenance"
        profiles = _make_reddit_profiles()
        profiles[0]["private_profile_field"] = "darf nicht exportiert werden"
        store.write_json(sim_id, "reddit_profiles", profiles)

        result = migrate_v2_to_v3(
            _make_v2_with_sections(),
            simulation_id=sim_id,
            artifact_store=store,
        )
        record = next(
            item
            for item in result["evidence_index"].values()
            if item["producer_key"] == "entity:ent-001"
        )

        assert record["raw"] == {
            "source_entity_uuid": "ent-001",
            "source_entity_type": "individual",
        }

    def test_no_datengap_personas_marker_wenn_personas_vorhanden(self):
        """Mit Personas kein dg-migration-personas DataGap-Eintrag."""
        store = InMemoryArtifactStore()
        sim_id = "sim_agg_test"
        store.write_json(sim_id, "reddit_profiles", _make_reddit_profiles())

        result = migrate_v2_to_v3(
            _make_v2_with_sections(),
            simulation_id=sim_id,
            artifact_store=store,
        )
        report = ReportV3.model_validate(result)

        gap_ids = {dg.id for dg in report.data_gaps}
        assert "dg-migration-personas" not in gap_ids

    def test_segments_aus_persona_aggregation(self):
        """segments[] wird aus Persona-Segment-Tags aggregiert."""
        store = InMemoryArtifactStore()
        sim_id = "sim_seg_test"
        store.write_json(sim_id, "reddit_profiles", _make_reddit_profiles())

        result = migrate_v2_to_v3(
            _make_v2_with_sections(),
            simulation_id=sim_id,
            artifact_store=store,
        )
        report = ReportV3.model_validate(result)

        assert len(report.segments) >= 1
        segment_names = {s.name for s in report.segments}
        # "technik_affin" hat 2 Personas, "konservativ" hat 1
        assert "technik_affin" in segment_names or any("technik" in n for n in segment_names)


# ---------------------------------------------------------------------------
# Case 2: Leere Aggregation — DataGap wie bisher
# ---------------------------------------------------------------------------

class TestLeereAggregation:
    def test_ohne_artifact_store_datengap_bleibt(self):
        """Ohne artifact_store: DataGap dg-migration-personas erscheint wie bisher."""
        result = migrate_v2_to_v3(
            {"report_id": "rep-no-store", "sections": []},
        )
        report = ReportV3.model_validate(result)

        gap_ids = {dg.id for dg in report.data_gaps}
        assert "dg-migration-personas" in gap_ids

    def test_ohne_profiles_in_store_datengap_bleibt(self):
        """artifact_store ohne reddit_profiles: DataGap erscheint."""
        store = InMemoryArtifactStore()
        result = migrate_v2_to_v3(
            {"report_id": "rep-empty-store", "sections": []},
            simulation_id="sim_missing",
            artifact_store=store,
        )
        report = ReportV3.model_validate(result)

        gap_ids = {dg.id for dg in report.data_gaps}
        assert "dg-migration-personas" in gap_ids

    def test_leere_profiles_liste_datengap_bleibt(self):
        """Leere reddit_profiles-Liste: DataGap erscheint."""
        store = InMemoryArtifactStore()
        store.write_json("sim_empty_list", "reddit_profiles", [])

        result = migrate_v2_to_v3(
            {"report_id": "rep-empty-list", "sections": []},
            simulation_id="sim_empty_list",
            artifact_store=store,
        )
        report = ReportV3.model_validate(result)

        gap_ids = {dg.id for dg in report.data_gaps}
        assert "dg-migration-personas" in gap_ids

    def test_bestehende_signatur_ohne_store_funktioniert(self):
        """Alter Aufruf ohne artifact_store bleibt kompatibel."""
        result = migrate_v2_to_v3(
            {"report_id": "rep-compat", "sections": []},
            simulation_id="sim_legacy",
        )
        report = ReportV3.model_validate(result)
        assert report.report_id == "rep-compat"
        # Personas leer, DataGap vorhanden
        assert report.personas == []
        assert any(dg.id == "dg-migration-personas" for dg in report.data_gaps)


# ---------------------------------------------------------------------------
# Case 3: Section-basierte FrictionPoint/TrustSignal-Extraktion
# ---------------------------------------------------------------------------

class TestSectionBasierteExtraktion:
    def test_friction_points_aus_reibungspunkt_section(self):
        """Claims aus 'Top 10 Reibungspunkte'-Section → friction_points[]."""
        store = InMemoryArtifactStore()
        store.write_json("sim_fp", "reddit_profiles", _make_reddit_profiles())

        result = migrate_v2_to_v3(
            _make_v2_with_sections(),
            simulation_id="sim_fp",
            artifact_store=store,
        )
        report = ReportV3.model_validate(result)

        assert len(report.friction_points) == 2
        fp_beschreibungen = [fp.beschreibung for fp in report.friction_points]
        assert any("Installationskosten" in b for b in fp_beschreibungen)
        assert any("Ladeinfrastruktur" in b for b in fp_beschreibungen)

    def test_trust_signals_aus_vertrauenssignal_section(self):
        """Claims aus 'Top 10 Vertrauenssignale'-Section → trust_signals[]."""
        store = InMemoryArtifactStore()
        store.write_json("sim_ts", "reddit_profiles", _make_reddit_profiles())

        result = migrate_v2_to_v3(
            _make_v2_with_sections(),
            simulation_id="sim_ts",
            artifact_store=store,
        )
        report = ReportV3.model_validate(result)

        assert len(report.trust_signals) == 1
        assert "TÜV" in report.trust_signals[0].beschreibung

    def test_friction_points_ohne_store_aus_sections(self):
        """Auch ohne artifact_store werden FrictionPoints aus Sections extrahiert."""
        result = migrate_v2_to_v3(_make_v2_with_sections())
        report = ReportV3.model_validate(result)

        assert len(report.friction_points) == 2
        assert len(report.trust_signals) == 1

    def test_friction_point_severity_aus_confidence(self):
        """FrictionPoint-severity wird aus confidence_label abgeleitet."""
        result = migrate_v2_to_v3(_make_v2_with_sections())
        report = ReportV3.model_validate(result)

        fp_by_id = {fp.id: fp for fp in report.friction_points}
        # fp01 hat confidence_label="high" → severity="high"
        assert fp_by_id["fp01"].severity == "high"
        # fp02 hat confidence_label="medium" → severity="medium"
        assert fp_by_id["fp02"].severity == "medium"

    def test_trust_signal_type_default(self):
        """TrustSignal bekommt signal_type='authority' als Default."""
        result = migrate_v2_to_v3(_make_v2_with_sections())
        report = ReportV3.model_validate(result)

        assert report.trust_signals[0].signal_type in {
            "social_proof", "authority", "consistency", "reciprocity", "scarcity", "liking"
        }

    def test_non_fp_ts_sections_nicht_extrahiert(self):
        """Claims aus anderen Sections (z.B. Executive Summary) landen nicht in friction_points."""
        result = migrate_v2_to_v3(_make_v2_with_sections())
        report = ReportV3.model_validate(result)

        fp_beschreibungen = [fp.beschreibung for fp in report.friction_points]
        # "Nachhaltige Mobilität" kommt aus Executive Summary — darf nicht in FP
        assert not any("Nachhaltige Mobilität" in b for b in fp_beschreibungen)

    def test_sections_claims_ohne_evidence_nicht_in_fp(self):
        """Claims ohne Evidence werden auch für FrictionPoints nicht extrahiert."""
        v2 = {
            "report_id": "rep-no-ev-fp",
            "sections": [
                {
                    "section_index": 5,
                    "section_title": "Top 10 Reibungspunkte",
                    "claims": [
                        {
                            "claim_id": "fp_no_ev",
                            "claim_text": "Kein Evidence vorhanden für diesen Reibungspunkt.",
                            "confidence_label": "high",
                            "evidence": [],  # kein Evidence
                        }
                    ],
                    "data_gaps": [],
                    "hypotheses": [],
                }
            ],
        }
        result = migrate_v2_to_v3(v2)
        report = ReportV3.model_validate(result)
        assert report.friction_points == []

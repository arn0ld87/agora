import json
from typing import Dict

from app.services.report_agent import Report, ReportAgent, ReportManager, ReportOutline, ReportSection, ReportStatus


def test_get_progress_returns_none_for_invalid_json(tmp_path, monkeypatch):
    monkeypatch.setattr(ReportManager, 'REPORTS_DIR', str(tmp_path))
    report_id = 'report_abcdef123456'
    report_dir = tmp_path / report_id
    report_dir.mkdir(parents=True)
    (report_dir / 'progress.json').write_text('', encoding='utf-8')

    assert ReportManager.get_progress(report_id) is None


def test_get_report_returns_none_for_invalid_meta_json(tmp_path, monkeypatch):
    monkeypatch.setattr(ReportManager, 'REPORTS_DIR', str(tmp_path))
    report_id = 'report_abcdef123456'
    report_dir = tmp_path / report_id
    report_dir.mkdir(parents=True)
    (report_dir / 'meta.json').write_text('', encoding='utf-8')

    assert ReportManager.get_report(report_id) is None


def test_update_progress_and_save_report_use_readable_json(tmp_path, monkeypatch):
    monkeypatch.setattr(ReportManager, 'REPORTS_DIR', str(tmp_path))
    report_id = 'report_abcdef123456'

    ReportManager.update_progress(
        report_id,
        status='processing',
        progress=42,
        message='Working',
        current_section='Intro',
        completed_sections=['Outline'],
    )
    progress = ReportManager.get_progress(report_id)
    assert progress['progress'] == 42
    assert progress['current_section'] == 'Intro'

    report = Report(
        report_id=report_id,
        simulation_id='sim_abcdef123456',
        graph_id='graph_abcdef123456',
        simulation_requirement='Test requirement',
        status=ReportStatus.COMPLETED,
        outline=ReportOutline(
            title='Demo',
            summary='Summary',
            sections=[ReportSection(title='Intro', content='Body')],
        ),
        markdown_content='# Demo\n\nBody',
        created_at='2026-04-23T00:00:00',
        completed_at='2026-04-23T00:05:00',
    )
    ReportManager.save_report(report)

    with open(tmp_path / report_id / 'meta.json', 'r', encoding='utf-8') as handle:
        raw = json.load(handle)
    assert raw['report_id'] == report_id

    loaded = ReportManager.get_report(report_id)
    assert loaded is not None
    assert loaded.report_id == report_id
    assert loaded.status == ReportStatus.COMPLETED


def test_is_claim_candidate_filters_markdown_headers_and_bold_titles():
    """S3a: Überschriften und Bold-Section-Titel sind keine Claims."""
    is_claim = ReportAgent._is_claim_candidate

    assert is_claim("Das Land NRW beschloss am 22. Mai 2024 die Einführung.") is True
    assert is_claim("**Diese Bold-Zeile ist lang genug acht zehn Wörter zu überschreiten klar erkennbar**") is True

    assert is_claim("# Hauptüberschrift") is False
    assert is_claim("## Sub-Heading") is False
    assert is_claim("### Tertiary") is False
    assert is_claim("**Der Beschluss und seine Architekten**") is False
    assert is_claim("- **Was passiert ist**") is False
    assert is_claim("") is False
    assert is_claim("   ") is False


def test_atomize_claim_chunk_splits_multisentence():
    """S3b: ein Mehrsatz-Chunk wird in atomare Sätze zerlegt."""
    atoms = ReportAgent._atomize_claim_chunk(
        "Ministerin Feller erklärte die Pläne. Die GEW kritisiert den Zeitplan. "
        "Die RWTH unterstützt das Curriculum."
    )
    assert len(atoms) == 3
    assert all(a.endswith(".") for a in atoms)


def test_is_atomic_claim_filters_short_and_unverbose():
    """S3b: Atom-Satz ohne Verb oder zu kurz wird verworfen."""
    is_atomic = ReportAgent._is_atomic_claim

    assert is_atomic("Das Land NRW beschloss die Einführung des Pflichtfachs.") is True
    assert is_atomic("Die Schule kritisiert den Zeitplan") is True
    assert is_atomic("Außerdem.") is False  # zu kurz
    assert is_atomic("Hier weiter mit") is False  # kein Satzende, kein Verb-Hint
    assert is_atomic("") is False


def test_build_claims_for_section_drops_headers():
    """S3a: Markdown-Header werden vor der Evidence-Bindung verworfen."""
    agent = ReportAgent.__new__(ReportAgent)
    agent._active_section_evidence = []
    agent.evidence_map = {"global_evidence": []}

    content = (
        "## Übersicht\n\n"
        "**Der Beschluss und seine Architekten**\n\n"
        "Das Land NRW beschloss am 22. Mai 2024 die Einführung des Pflichtfachs.\n\n"
        "Ministerin Feller erklärte: Wir setzen den Beschluss bis 2027/28 um."
    )

    claims = agent._build_claims_for_section(content)

    texts = [c["claim_text"] for c in claims]
    assert all("##" not in t for t in texts)
    assert not any(t.startswith("**Der Beschluss") for t in texts)
    assert len(claims) == 2


def test_build_claims_uses_embedder_and_emits_match_score():
    """S4b: bei verfügbarem Embedder bekommt jeder Claim ein gerankt-
    gefiltertes Evidence-Set mit match_score."""
    agent = ReportAgent.__new__(ReportAgent)
    agent._active_section_evidence = [
        {"type": "graph_fact", "source": "report_tool",
         "snippet": "NRW Pflichtfach KIDM Curriculum"},
        {"type": "graph_fact", "source": "report_tool",
         "snippet": "Bayern plant nichts dergleichen"},
    ]
    agent.evidence_map = {
        "schema_version": 2,
        "global_evidence": [
            {"type": "graph_metric", "source": "simulation_metrics",
             "snippet": "echo_chamber_index 0.42"},
        ],
    }
    vocab: Dict[str, int] = {}

    def embed(text):
        vec = [0.0] * 16
        for tok in (text or "").lower().split():
            vocab.setdefault(tok, len(vocab) % 16)
            vec[vocab[tok]] += 1.0
        return vec

    agent._embed_cache = embed

    claims = agent._build_claims_for_section("NRW Pflichtfach KIDM Curriculum startet 2027.")

    assert len(claims) == 1
    bound_evidence = claims[0]["evidence"]
    matches = [e for e in bound_evidence if "match_score" in e]
    assert matches, "Erwarte mindestens ein gebundenes Evidence-Item"
    assert not any("Bayern" in (e.get("snippet") or "") for e in matches)


def test_init_evidence_map_sets_schema_version_2(monkeypatch):
    """S4b: neue Evidence-Maps tragen schema_version=2."""
    agent = ReportAgent.__new__(ReportAgent)
    agent.simulation_id = "sim_xyz"

    monkeypatch.setattr(
        ReportAgent,
        "_collect_simulation_evidence_items",
        lambda self: [],
    )
    agent._init_evidence_map("rep_001")
    assert agent.evidence_map["schema_version"] == 2


def test_report_claim_model_keeps_legacy_fields_and_numeric_score():
    agent = ReportAgent.__new__(ReportAgent)
    agent._active_section_evidence = [{
        "type": "graph_fact",
        "source": "report_tool",
        "snippet": "Agent group A repeatedly reposted group B.",
    }]
    agent.evidence_map = {
        "global_evidence": [{
            "type": "graph_metric",
            "source": "simulation_metrics",
            "value": "echo_chamber_index=0.64",
            "snippet": "echo_chamber_index: 0.64",
        }]
    }

    claims = agent._build_claims_for_section("Akteursgruppe A polarisiert die Diskussion.")

    assert claims[0]["claim"] == "Akteursgruppe A polarisiert die Diskussion."
    assert claims[0]["claim_text"] == "Akteursgruppe A polarisiert die Diskussion."
    # Sub-Slice 07: kein global_items-Fallback mehr — im Embedder-Fehler-Pfad
    # landen nur direct_items (graph_fact) in evidence_items. global_evidence
    # bleibt draußen.
    # S6: formelbasierte Confidence — relevance(0.5) + source_quality
    # (1.0 für graph_fact) + specificity(0.5) + consistency(0.6 für 1 Quelle)
    # = 0.40*0.5 + 0.25*1.0 + 0.20*0.5 + 0.15*0.6 = 0.64, Label "medium".
    assert claims[0]["confidence"] == "medium"
    assert claims[0]["confidence_score"] == 0.64
    assert claims[0]["evidence"] == claims[0]["evidence_items"]
    # S5: model_generated_inference darf nicht mehr im Evidence-Array sein.
    evidence_types = {item["type"] for item in claims[0]["evidence"]}
    assert "model_generated_inference" not in evidence_types
    # Nach Sub-Slice 07: nur noch graph_fact (kein global graph_metric-Leak)
    assert evidence_types == {"graph_fact"}
    # Statt dessen lebt die Synthese im audit_trail.
    audit_types = {item["type"] for item in claims[0].get("audit_trail", [])}
    assert "model_generated_inference" in audit_types


def test_collect_simulation_evidence_uses_metrics_and_actions(monkeypatch):
    from app.services.simulation_runner import AgentAction, SimulationRunner

    actions = [
        AgentAction(
            round_num=2,
            timestamp="2026-04-29T10:00:00",
            platform="twitter",
            agent_id=1,
            agent_name="Agent A",
            action_type="FOLLOW",
            action_args={"target_agent_id": 2},
        ),
        AgentAction(
            round_num=2,
            timestamp="2026-04-29T10:01:00",
            platform="twitter",
            agent_id=2,
            agent_name="Agent B",
            action_type="FOLLOW",
            action_args={"target_agent_id": 1},
        ),
    ]
    monkeypatch.setattr(SimulationRunner, "get_all_actions", classmethod(lambda cls, simulation_id: actions))
    agent = ReportAgent.__new__(ReportAgent)
    agent.simulation_id = "sim_abcdef123456"

    evidence = agent._collect_simulation_evidence_items()

    assert any(item["type"] == "graph_metric" and item["source"] == "simulation_metrics" for item in evidence)
    assert any(item["type"] == "agent_action" and item["source"] == "simulation_actions" for item in evidence)


def test_evidence_map_round_trip_updates_report_meta(tmp_path, monkeypatch):
    monkeypatch.setattr(ReportManager, 'REPORTS_DIR', str(tmp_path))
    report_id = 'report_abcdef123456'
    evidence_map = {
        "schema_version": 1,
        "report_id": report_id,
        "simulation_id": "sim_abcdef123456",
        "global_evidence": [],
        "sections": [{
            "section_index": 1,
            "section_title": "Intro",
            "claims": [{
                "claim_id": "claim_01",
                "claim": "A claim",
                "claim_text": "A claim",
                "confidence": "medium",
                "confidence_score": 0.62,
                "evidence": [{"type": "graph_metric", "source": "simulation_metrics"}],
                "evidence_items": [{"type": "graph_metric", "source": "simulation_metrics"}],
            }],
        }],
    }
    ReportManager.save_evidence_map(report_id, evidence_map)
    report = Report(
        report_id=report_id,
        simulation_id='sim_abcdef123456',
        graph_id='graph_abcdef123456',
        simulation_requirement='Test requirement',
        status=ReportStatus.COMPLETED,
        markdown_content='# Demo',
    )

    ReportManager.save_report(report)
    loaded = ReportManager.get_report(report_id)

    assert ReportManager.get_evidence_map(report_id)["sections"][0]["claims"][0]["confidence_score"] == 0.62
    assert loaded.has_evidence is True
    assert loaded.evidence_sections == 1

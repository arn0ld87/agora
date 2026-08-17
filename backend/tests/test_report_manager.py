import json
from typing import Dict

from app.services.report_agent import Report, ReportAgent, ReportManager, ReportOutline, ReportSection, ReportStatus
from app.services.report_agent.sections import render_data_gaps_for_section


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


def test_is_claim_candidate_verwirft_markup_und_zitatzeilen():
    """#1316: Zitatblöcke und Tag-Zeilen sind Markup, keine Aussagen."""
    is_claim = ReportAgent._is_claim_candidate

    # Zitatblock — das ist Evidenz, keine Behauptung des Berichts.
    assert is_claim('> "Ich halte den Zeitplan für zu eng." — Persona 4') is False
    assert is_claim("| Zitat aus der Simulation mit ausreichend vielen Wörtern") is False

    # Vollständig getaggte Zeile.
    assert is_claim('<simulated_quote persona_id="p4" seed_anchor="ev_1">') is False

    # Rest-Markup, roh wie HTML-escapt, auch mitten in der Zeile.
    assert is_claim(
        "Die Personas äußerten sich wie folgt: <simulated_quote persona_id=\"p4\">"
    ) is False
    assert is_claim(
        "Die Personas äußerten sich wie folgt: &lt;simulated_quote&gt;"
    ) is False
    assert is_claim("Der Abschnitt endet hier. &lt;/simulated_quote&gt;") is False

    # Gegenprobe: eine gewöhnliche Aussage bleibt Kandidat.
    assert is_claim("Das Land NRW beschloss am 22. Mai 2024 die Einführung.") is True
    # Ein Kleiner-als-Zeichen allein macht noch kein Markup.
    assert is_claim("Die Zustimmung lag bei < 40 Prozent der befragten Personas.") is True


def test_is_atomic_claim_verwirft_gliederungsansagen():
    """#1316: Eine Ankündigung behauptet nichts und kann nichts belegen."""
    is_atomic = ReportAgent._is_atomic_claim

    assert is_atomic("Im Folgenden werden die Reaktionsmuster dargestellt.") is False
    assert is_atomic("Der folgende Vergleich ordnet die drei Varianten ein.") is False
    assert is_atomic("Dieser Abschnitt fasst die Konfliktlinien zusammen.") is False
    assert is_atomic("Nachfolgend wird die Segmentstruktur erläutert.") is False
    assert is_atomic("Zunächst wird die Ausgangslage beschrieben.") is False
    assert is_atomic("Abschließend werden die Restrisiken betrachtet.") is False
    assert is_atomic(
        "Die Positionen der Gruppen werden im Folgenden entlang zentraler "
        "Dimensionen beschrieben."
    ) is False


def test_is_atomic_claim_behaelt_aussagen_mit_aehnlichem_wortlaut():
    """#1316: Der Filter ist eng — echte Aussagen dürfen nicht mitfallen."""
    is_atomic = ReportAgent._is_atomic_claim

    # "wird beschrieben" ohne Folgend-Verweis ist eine Aussage über die Sache.
    assert is_atomic(
        "Die Personagruppe wird in den Interviews als skeptisch beschrieben."
    ) is True
    # "Folgen" als Substantiv, nicht als Gliederungsverweis.
    assert is_atomic(
        "Die Folgen des Beschlusses wurden von acht Personas benannt."
    ) is True
    assert is_atomic(
        "Der folgende Tag brachte laut Simulation keine neue Reaktion."
    ) is False  # bewusst in Kauf genommen: Satzanfang schlägt Bedeutung


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


def test_build_claims_verwirft_gliederungsabsatz_auch_ueber_den_fallback():
    """#1316: der Chunk-Fallback holte den verworfenen Metasatz zurueck.

    ``_build_claims_for_section`` faellt auf den ganzen Chunk zurueck, wenn
    kein Atom den Filter passiert — damit eine legitime Single-Sentence-
    Section nicht verschwindet. Steht die Gliederungsansage als eigener
    Absatz, war ``atoms`` genau deshalb leer, und ``atoms or [chunk]`` setzte
    den Satz unveraendert wieder ein. Der Helfer-Test allein haette das nicht
    gefangen.
    """
    agent = ReportAgent.__new__(ReportAgent)
    agent._active_section_evidence = []
    agent.evidence_map = {"global_evidence": []}

    content = (
        "Im Folgenden werden die Reaktionsmuster dargestellt.\n\n"
        "Das Land NRW beschloss am 22. Mai 2024 die Einführung des Pflichtfachs."
    )

    claims = agent._build_claims_for_section(content)

    texts = [c["claim_text"] for c in claims]
    assert not any("Im Folgenden" in t for t in texts), (
        f"Die Gliederungsansage darf kein Claim werden, war aber in: {texts!r}"
    )
    assert len(claims) == 1


def test_build_claims_behaelt_einzelsatz_absatz_ohne_satzende():
    """Gegenprobe: der Fallback muss weiterhin greifen.

    Ein Absatz ohne Satzendezeichen und ohne Verb-Hint passiert
    ``is_atomic_claim`` nicht — ohne Fallback ginge er verloren. Nur
    Gliederungsansagen sind ausgenommen, nicht alles, was der Atom-Filter
    ablehnt.
    """
    agent = ReportAgent.__new__(ReportAgent)
    agent._active_section_evidence = []
    agent.evidence_map = {"global_evidence": []}

    claims = agent._build_claims_for_section("Drei Varianten im direkten Vergleich")

    assert [c["claim_text"] for c in claims] == [
        "Drei Varianten im direkten Vergleich"
    ]


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


def test_init_evidence_map_sets_schema_version_3(monkeypatch):
    """Kanonische Evidence-Maps tragen den ID-Vertrag schema_version=3."""
    agent = ReportAgent.__new__(ReportAgent)
    agent.simulation_id = "sim_xyz"

    monkeypatch.setattr(
        ReportAgent,
        "_collect_simulation_evidence_items",
        lambda self: [],
    )
    agent._init_evidence_map("rep_001")
    assert agent.evidence_map["schema_version"] == 3


def test_report_claim_model_keeps_legacy_fields_and_numeric_score():
    agent = ReportAgent.__new__(ReportAgent)
    # Embedder deterministisch deaktivieren — der Test prüft den
    # Fallback-Pfad ohne EmbeddingService. Ohne diesen Reset würde
    # `_try_get_embedder` in Umgebungen mit lebendem Ollama eine echte
    # Embedder-Funktion liefern und das Binding mit threshold=0.55
    # liesse `bound=[]` zurück — der Anti-Dekorations-Guard kippt
    # confidence dann auf "low", obwohl der Test den Embedder-Fehler-
    # Pfad prüfen will (siehe Sub-Slice-07-Kommentar unten).
    agent._embed_cache = None
    agent._active_section_evidence = [
        {
            "type": "graph_fact",
            "source": "report_tool",
            "snippet": "Agent group A repeatedly reposted group B.",
        },
        {
            "type": "graph_fact",
            "source": "report_tool",
            "snippet": "Agent group A reaches group C twice within window.",
        },
    ]
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
    # S6 + Slice-S1-Floor: 2 graph_facts (gleiche type+source) → Floor-Cap greift nicht
    # (len==2, Bedingung len<2 ist False). consistency: 1 unique (type,source)-Paar → 0.6.
    # relevance(0.5) + source_quality(1.0) + specificity(0.5) + consistency(0.6)
    # = 0.40*0.5 + 0.25*1.0 + 0.20*0.5 + 0.15*0.6 = 0.64, Label "low" (Slice-2: < 0.65).
    # Freie ``report_tool``-Strings besitzen keinen Producer-Key und dürfen
    # deshalb weder Confidence noch Claim-Status dekorativ erhöhen.
    assert claims[0]["confidence"] == "speculative"
    assert claims[0]["confidence_score"] == 0.15
    assert claims[0]["evidence"] == claims[0]["evidence_items"]
    # S5: model_generated_inference darf nicht mehr im Evidence-Array sein.
    evidence_types = {item["type"] for item in claims[0]["evidence"]}
    assert "model_generated_inference" not in evidence_types
    # Ohne stabilen Producer-Key bleibt auch graph_fact reine Audit-Evidence.
    assert evidence_types == set()
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


def test_assemble_full_report_renders_confidence_markers(tmp_path, monkeypatch):
    """P2.2: Low-/Medium-Confidence-Claims sind im exportierten Markdown sichtbar."""
    monkeypatch.setattr(ReportManager, 'REPORTS_DIR', str(tmp_path))
    report_id = 'report_abcdef123456'
    outline = ReportOutline(
        title='Demo',
        summary='Summary',
        sections=[ReportSection(title='Intro', content='Body')],
    )
    ReportManager.save_section(
        report_id,
        1,
        ReportSection(title='Intro', content='Abschnittstext.'),
    )
    ReportManager.save_evidence_map(report_id, {
        "schema_version": 2,
        "report_id": report_id,
        "simulation_id": "sim_abcdef123456",
        "global_evidence": [],
        "sections": [{
            "section_index": 1,
            "section_title": "Intro",
            "section_summary": "Abschnittstext.",
            "claims": [
                {
                    "claim_id": "claim_01",
                    "claim_text": "Eine schwach belegte Beobachtung bleibt sichtbar markiert.",
                    "confidence_label": "low",
                    "confidence_score": 0.15,
                    "evidence": [],
                    "audit_trail": [],
                },
                {
                    "claim_id": "claim_02",
                    "claim_text": "Eine mittel belegte Beobachtung bekommt einen dezenten Marker.",
                    "confidence_label": "medium",
                    "confidence_score": 0.55,
                    "evidence": [{"type": "graph_metric", "source": "s", "snippet": "metric"}],
                    "audit_trail": [],
                },
            ],
        }],
    })

    markdown = ReportManager.assemble_full_report(report_id, outline)

    assert markdown.count("Low-Confidence-Hinweis") == 1
    assert "score=0.15" in markdown
    assert "medium-confidence" in markdown
    assert "score=0.55" in markdown


def test_assemble_full_report_marks_hypotheses_and_renders_section_data_gaps(
    tmp_path, monkeypatch
):
    """#1232: Unbelegte Sätze bleiben im Fließtext nicht als Feststellung stehen."""
    monkeypatch.setattr(ReportManager, "REPORTS_DIR", str(tmp_path))
    report_id = "report_abcdef123456"
    hypothesis_text = "Der Kipppunkt tritt ein, sobald die Akzeptanz sinkt."
    appendix_hypothesis_text = "Ein zweiter Kipppunkt bleibt ebenfalls unbelegt."
    outline = ReportOutline(
        title="Demo",
        summary="Summary",
        sections=[ReportSection(title="Intro", content="Body")],
    )
    ReportManager.save_section(
        report_id,
        1,
        ReportSection(
            title="Intro",
            content=(
                f"{hypothesis_text}\n\n{appendix_hypothesis_text}\n\n"
                "Ein belegter Kontext bleibt unverändert."
            ),
        ),
    )
    ReportManager.save_evidence_map(report_id, {
        "schema_version": 2,
        "report_id": report_id,
        "simulation_id": "sim_abcdef123456",
        "global_evidence": [],
        "sections": [{
            "section_index": 1,
            "section_title": "Intro",
            "section_summary": "Abschnittstext.",
            "claims": [],
            "hypotheses": [{
                "hypothesis_id": "hypothesis_01",
                "hypothesis_text": hypothesis_text,
                "rationale": "Keine stützende Evidence gebunden.",
                "suggested_evidence": ["Stakeholder-Interview nacherheben"],
            }],
            "hypotheses_appendix": [{
                "hypothesis_id": "hypothesis_06",
                "hypothesis_text": appendix_hypothesis_text,
                "rationale": "Mehr als fünf Hypothesen in diesem Abschnitt.",
                "suggested_evidence": [],
            }],
            "data_gaps": [{
                "gap_id": "gap_01",
                "claim_text": hypothesis_text,
                "gap_reason": "no_evidence_bound",
                "suggested_fix": "Stakeholder-Interview nacherheben",
            }],
        }],
    })

    markdown = ReportManager.assemble_full_report(report_id, outline)
    narrative = markdown.split("### Hypothesen ohne Evidence", 1)[0]

    assert f"**Hypothese (unbelegt):** {hypothesis_text}" in narrative
    assert f"**Hypothese (unbelegt):** {appendix_hypothesis_text}" in narrative
    assert "Ein belegter Kontext bleibt unverändert." in narrative
    assert "### Hypothesen ohne Evidence" in markdown
    assert "### Datenlücken dieses Abschnitts" in markdown
    assert "**gap_01:**" in markdown
    assert "no_evidence_bound" in markdown
    assert "Stakeholder-Interview nacherheben" in markdown


def test_hypothesis_marker_is_set_once_per_hypothesis() -> None:
    """#1315: `re.sub` ohne `count` markierte jedes Vorkommen.

    Wiederholt der Fließtext dieselbe Formulierung — bei generierter Prosa der
    Normalfall —, stand der Marker mehrfach im selben Abschnitt.
    """
    from app.services.report_agent.sections import mark_hypotheses_in_content

    hypothesis = "Der Kipppunkt tritt ein, sobald die Akzeptanz sinkt."
    content = f"{hypothesis} Anderer Satz. {hypothesis}"
    section = {"hypotheses": [{"hypothesis_text": hypothesis}]}

    rendered = mark_hypotheses_in_content(content, section)

    assert rendered.count("**Hypothese (unbelegt):**") == 1


def test_hypothesis_marker_does_not_nest_inside_a_longer_hypothesis() -> None:
    """#1315: Teilstring-Hypothesen erzeugten Marker im Marker.

    Die Sortierung nach Länge markierte zuerst die lange Hypothese; die kurze
    traf danach dieselbe Stelle erneut. Das war die Quelle der beobachteten
    drei Marker in einem Absatz.
    """
    from app.services.report_agent.sections import mark_hypotheses_in_content

    long_hypothesis = "Ein gestaffelter Start hält die Reaktionen am stabilsten."
    short_hypothesis = "hält die Reaktionen am stabilsten"
    section = {
        "hypotheses": [
            {"hypothesis_text": long_hypothesis},
            {"hypothesis_text": short_hypothesis},
        ]
    }

    rendered = mark_hypotheses_in_content(long_hypothesis, section)

    assert rendered.count("**Hypothese (unbelegt):**") == 1
    assert rendered == f"**Hypothese (unbelegt):** {long_hypothesis}"


def test_hypothesis_marker_falls_back_to_a_later_independent_occurrence() -> None:
    """#1315: ein ueberlappender Ersttreffer darf die Hypothese nicht verwerfen.

    Kommt eine kurze Hypothese zuerst innerhalb einer laengeren, bereits
    beanspruchten vor, spaeter aber eigenstaendig, muss der eigenstaendige
    Satz markiert werden. Ein `re.search` haette nur den ueberlappenden
    Treffer gesehen und die Hypothese ganz fallen lassen.
    """
    from app.services.report_agent.sections import mark_hypotheses_in_content

    long_hypothesis = "Ein gestaffelter Start hält die Reaktionen am stabilsten."
    short_hypothesis = "hält die Reaktionen am stabilsten"
    content = f"{long_hypothesis} Danach folgt Prosa. Auch Variante B {short_hypothesis}."
    section = {
        "hypotheses": [
            {"hypothesis_text": long_hypothesis},
            {"hypothesis_text": short_hypothesis},
        ]
    }

    rendered = mark_hypotheses_in_content(content, section)

    assert rendered.count("**Hypothese (unbelegt):**") == 2
    assert f"**Hypothese (unbelegt):** {long_hypothesis}" in rendered
    assert f"Auch Variante B **Hypothese (unbelegt):** {short_hypothesis}" in rendered


def test_strip_raw_html_markers_converts_badges_to_bold() -> None:
    """#1315: Fallback-Sanitizer fuer den .md-Export ohne HTML-Renderer."""
    from app.services.report_agent.sections import strip_raw_html_markers

    content = (
        'Text davor. > <span class="conf-badge conf-low">⚠️ Low (score=0.59)</span>: '
        'Claim. Und <span class="conf-badge conf-medium">medium (score=0.7)</span>.'
    )

    stripped = strip_raw_html_markers(content)

    assert "<span" not in stripped
    assert "**⚠️ Low (score=0.59)**" in stripped
    assert "**medium (score=0.7)**" in stripped
    assert "Text davor." in stripped


def test_appendix_hypotheses_stay_marked_and_are_accounted_for() -> None:
    """#1315 darf #1232 nicht aufweichen.

    Appendix-Hypothesen sind genauso unbelegt wie die sichtbaren fünf und
    bleiben deshalb im Fließtext markiert. Neu ist, dass die Liste darunter
    ihre Zahl ausweist — vorher zeigte der Marker auf eine Aufzählung, die den
    Satz nicht enthielt.
    """
    from app.services.report_agent.sections import (
        mark_hypotheses_in_content,
        render_hypotheses_for_section,
    )

    visible = "Die sichtbare Hypothese bleibt unbelegt."
    appendix = "Die Appendix-Hypothese bleibt ebenfalls unbelegt."
    section = {
        "hypotheses": [{"hypothesis_id": "hypothesis_01", "hypothesis_text": visible}],
        "hypotheses_appendix": [
            {"hypothesis_id": "hypothesis_06", "hypothesis_text": appendix}
        ],
    }

    rendered = mark_hypotheses_in_content(f"{visible}\n\n{appendix}", section)
    assert f"**Hypothese (unbelegt):** {visible}" in rendered
    assert f"**Hypothese (unbelegt):** {appendix}" in rendered

    listing = render_hypotheses_for_section(section)
    assert "hypothesis_01" in listing
    assert "1 weitere markierte Hypothese" in listing


def test_confidence_marker_has_a_markdown_variant_without_raw_html() -> None:
    """#1315: das `<span class="conf-badge">` stand unrendert im .md-Export."""
    from app.services.report_agent.sections import render_claim_to_markdown

    claim = {
        "claim_text": "Eine Aussage mit niedriger Konfidenz.",
        "confidence_label": "low",
        "confidence_score": 0.59,
    }

    html_variant = render_claim_to_markdown(claim)
    markdown_variant = render_claim_to_markdown(claim, raw_html=False)

    assert '<span class="conf-badge' in html_variant, "HTML-/Print-Pfad unverändert"
    assert "<span" not in markdown_variant
    assert "score=0.59" in markdown_variant
    assert "Eine Aussage mit niedriger Konfidenz." in markdown_variant


def test_section_data_gaps_are_capped_without_hiding_the_remainder_count() -> None:
    section = {
        "data_gaps": [
            {
                "gap_id": f"gap_{index:02d}",
                "claim_text": f"Unbelegte Aussage Nummer {index} braucht weitere Daten.",
                "gap_reason": "no_evidence_bound",
            }
            for index in range(1, 8)
        ]
    }

    markdown = render_data_gaps_for_section(section)

    assert "**gap_05:**" in markdown
    assert "gap_06" not in markdown
    assert "2 weitere Datenlücken" in markdown
    assert "Evidence-Export" in markdown


def test_clean_section_content_renders_simulated_quote_marker() -> None:
    content = (
        '<simulated_quote persona_id="persona_10" '
        'seed_anchor="seed_doc:robert_krasniqi_statement">'
        'Meine Generation will keine 5-Tage-Woche mehr.'
        '</simulated_quote>'
    )

    cleaned = ReportManager._clean_section_content(content, "Persona-O-Ton")

    assert "**Simulierter Persona-O-Ton**" in cleaned
    assert "persona_id: persona_10" in cleaned
    assert "seed_anchor: seed_doc:robert_krasniqi_statement" in cleaned
    assert "Meine Generation will keine 5-Tage-Woche mehr." in cleaned
    assert "<simulated_quote" not in cleaned

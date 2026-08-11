"""
TDD-Tests für M11.8e — validate_quote_anchors() in report_agent/evidence.py.

Prüft:
1. Happy-Path: 2 gültige Quotes → valid=True
2. Quote ohne persona_id → invalid_quotes populated, valid=False
3. Quote ohne seed_anchor → invalid_quotes populated, valid=False
4. Quote mit seed_anchor nicht in EvidenceMap → unbound_evidence_refs, valid=False
5. Quote mit seed_anchor="seed_doc:abc" → valid=True (opaque seed_doc-Prefix OK)
6. Quote mit unbekannter persona_id → invalid_quotes, valid=False
7. Mehrere Quotes, einer kaputt → invalid_quotes enthält genau diesen
8. Leere Section (keine Quote-Tags) → quotes=[], valid=True (Aufrufer entscheidet)
"""
from __future__ import annotations


from app.services.report_agent.evidence import validate_quote_anchors, QuoteValidationResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_evidence_map(source_id_anchors: list[str] | None = None) -> dict:
    """Erstellt eine minimale Evidence-Map mit optionalen source_id_anchors."""
    items = []
    for anchor in (source_id_anchors or []):
        items.append({
            "type": "graph_fact",
            "source": "test-source",
            "snippet": "Test-Snippet für Anchor",
            "source_id_anchor": anchor,
        })
    return {
        "schema_version": 2,
        "report_id": "report_test",
        "simulation_id": "sim_test",
        "global_evidence": items,
        "sections": [],
    }


def _make_quote_tag(
    persona_id: str | None = "persona_01",
    seed_anchor: str | None = "ev_001",
    text: str = "Ich finde das Produkt überzeugend.",
) -> str:
    """Erstellt einen validen <simulated_quote>-Tag-String."""
    attrs = []
    if persona_id is not None:
        attrs.append(f'persona_id="{persona_id}"')
    if seed_anchor is not None:
        attrs.append(f'seed_anchor="{seed_anchor}"')
    attr_str = " ".join(attrs)
    return f'<simulated_quote {attr_str}>{text}</simulated_quote>'


# ---------------------------------------------------------------------------
# 1. Happy-Path: 2 gültige Quotes → valid=True
# ---------------------------------------------------------------------------

class TestValidateQuoteAnchorsHappyPath:
    def test_two_valid_quotes_returns_valid_true(self):
        """Zwei Quotes mit persona_id + seed_anchor in EvidenceMap → valid=True."""
        evidence_map = _make_evidence_map(["ev_001", "ev_002"])
        persona_ids = ["persona_01", "persona_02"]

        tag1 = _make_quote_tag(persona_id="persona_01", seed_anchor="ev_001")
        tag2 = _make_quote_tag(persona_id="persona_02", seed_anchor="ev_002", text="Klare Ablehnung.")
        section_text = f"Analyse:\n\n{tag1}\n\nWeitere Beobachtung:\n\n{tag2}"

        result = validate_quote_anchors(section_text, evidence_map, persona_ids)

        assert isinstance(result, QuoteValidationResult)
        assert result.valid is True
        assert len(result.quotes) == 2
        assert result.invalid_quotes == []
        assert result.unbound_evidence_refs == []

    def test_quotes_list_contains_correct_attributes(self):
        """Geparste Quotes enthalten persona_id, seed_anchor und text."""
        evidence_map = _make_evidence_map(["ev_100"])
        persona_ids = ["p_alpha"]
        text_content = "Das überzeugt mich nicht."

        tag = _make_quote_tag(persona_id="p_alpha", seed_anchor="ev_100", text=text_content)
        result = validate_quote_anchors(tag, evidence_map, persona_ids)

        assert result.valid is True
        assert len(result.quotes) == 1
        quote = result.quotes[0]
        assert quote["persona_id"] == "p_alpha"
        assert quote["seed_anchor"] == "ev_100"
        assert text_content in quote["text"]


# ---------------------------------------------------------------------------
# 2. Quote ohne persona_id → invalid_quotes, valid=False
# ---------------------------------------------------------------------------

class TestMissingPersonaId:
    def test_quote_without_persona_id_is_invalid(self):
        """Quote ohne persona_id-Attribut → invalid_quotes populated, valid=False."""
        evidence_map = _make_evidence_map(["ev_001"])
        persona_ids = ["persona_01"]

        # Tag ohne persona_id
        tag = '<simulated_quote seed_anchor="ev_001">Aussage ohne Persona.</simulated_quote>'
        result = validate_quote_anchors(tag, evidence_map, persona_ids)

        assert result.valid is False
        assert len(result.invalid_quotes) == 1
        assert result.invalid_quotes[0].get("reason") is not None or "persona_id" in str(result.invalid_quotes[0])


# ---------------------------------------------------------------------------
# 3. Quote ohne seed_anchor → invalid_quotes, valid=False
# ---------------------------------------------------------------------------

class TestMissingSeedAnchor:
    def test_quote_without_seed_anchor_is_invalid(self):
        """Quote ohne seed_anchor-Attribut → invalid_quotes populated, valid=False."""
        evidence_map = _make_evidence_map(["ev_001"])
        persona_ids = ["persona_01"]

        tag = '<simulated_quote persona_id="persona_01">Aussage ohne Anker.</simulated_quote>'
        result = validate_quote_anchors(tag, evidence_map, persona_ids)

        assert result.valid is False
        assert len(result.invalid_quotes) == 1


# ---------------------------------------------------------------------------
# 4. seed_anchor nicht in EvidenceMap → unbound_evidence_refs, valid=False
# ---------------------------------------------------------------------------

class TestUnboundSeedAnchor:
    def test_seed_anchor_not_in_evidence_map(self):
        """seed_anchor ohne Match in EvidenceMap → unbound_evidence_refs, valid=False."""
        evidence_map = _make_evidence_map(["ev_001"])  # ev_999 fehlt
        persona_ids = ["persona_01"]

        tag = _make_quote_tag(persona_id="persona_01", seed_anchor="ev_999")
        result = validate_quote_anchors(tag, evidence_map, persona_ids)

        assert result.valid is False
        assert "ev_999" in result.unbound_evidence_refs
        assert result.invalid_quotes == []  # Attribute vorhanden, nur Referenz fehlt


# ---------------------------------------------------------------------------
# 5. seed_anchor="seed_doc:abc" → valid=True (opaque OK)
# ---------------------------------------------------------------------------

class TestSeedDocPrefixWirdGebunden:
    """Issue #1249: Das ``seed_doc:``-Präfix ist keine Freikarte mehr.

    Dieser Test forderte bis zum Sign-off vom 2026-08-11 das Gegenteil — ein
    Anker mit diesem Präfix galt als opake Referenz und wurde nie aufgelöst.
    Genau diesen einen ungeprüften Pfad wählte das Modell in den beobachteten
    Läufen, mit dem Beispielwert aus dem Prompt: acht Zitate von sieben
    Personas trugen ``seed_doc:interview_transcript_07``, ein Dokument dieses
    Namens gab es nicht.

    Die Erwartung ist bewusst umgedreht, nicht abgeschwächt: Das Zitat bleibt
    gültig — verworfen wird nichts —, aber der Anker erscheint als
    ``unbound_evidence_refs`` und ist damit sichtbar.
    """

    def test_nicht_aufloesbarer_seed_doc_anker_wird_unbound(self):
        evidence_map = _make_evidence_map([])  # leere EvidenceMap
        persona_ids = ["persona_01"]

        tag = _make_quote_tag(persona_id="persona_01", seed_anchor="seed_doc:abc123")
        result = validate_quote_anchors(tag, evidence_map, persona_ids)

        assert result.unbound_evidence_refs == ["seed_doc:abc123"]
        # Die gewählte Politik verwirft nicht — der Inhalt bleibt erhalten.
        assert result.invalid_quotes == []


# ---------------------------------------------------------------------------
# 6. Unbekannte persona_id (nicht im Plan) → invalid_quotes, valid=False
# ---------------------------------------------------------------------------

class TestUnknownPersonaId:
    def test_unknown_persona_id_causes_invalid_quote(self):
        """persona_id nicht in persona_ids-Liste → invalid_quotes, valid=False."""
        evidence_map = _make_evidence_map(["ev_001"])
        persona_ids = ["persona_01"]  # persona_99 ist nicht dabei

        tag = _make_quote_tag(persona_id="persona_99", seed_anchor="ev_001")
        result = validate_quote_anchors(tag, evidence_map, persona_ids)

        assert result.valid is False
        assert len(result.invalid_quotes) == 1
        # persona_id soll als Ursache erkennbar sein
        invalid = result.invalid_quotes[0]
        assert "persona_99" in str(invalid)


# ---------------------------------------------------------------------------
# 7. Mehrere Quotes, einer kaputt → invalid_quotes enthält genau diesen
# ---------------------------------------------------------------------------

class TestPartiallyInvalidQuotes:
    def test_one_invalid_among_valid_quotes(self):
        """Mehrere Quotes, einer ohne persona_id → invalid_quotes enthält genau diesen."""
        evidence_map = _make_evidence_map(["ev_001", "ev_002"])
        persona_ids = ["persona_01", "persona_02"]

        valid_tag = _make_quote_tag(persona_id="persona_01", seed_anchor="ev_001", text="Valide Aussage.")
        invalid_tag = '<simulated_quote seed_anchor="ev_002">Aussage ohne Persona.</simulated_quote>'

        section_text = f"{valid_tag}\n\n{invalid_tag}"
        result = validate_quote_anchors(section_text, evidence_map, persona_ids)

        assert result.valid is False
        assert len(result.quotes) == 1  # nur der valide Quote
        assert len(result.invalid_quotes) == 1
        # Der invalide Quote soll auffindbar sein
        assert "ev_002" in str(result.invalid_quotes[0]) or "persona_id" in str(result.invalid_quotes[0])


# ---------------------------------------------------------------------------
# 8. Leere Section (keine Quote-Tags) → quotes=[], valid=True
# ---------------------------------------------------------------------------

class TestEmptySection:
    def test_no_quote_tags_returns_valid_true_with_empty_quotes(self):
        """Keine <simulated_quote>-Tags → quotes=[], valid=True (Aufrufer entscheidet ob Pflicht)."""
        evidence_map = _make_evidence_map([])
        persona_ids = ["persona_01"]

        section_text = "Diese Section enthält nur Fließtext ohne Persona-Zitate."
        result = validate_quote_anchors(section_text, evidence_map, persona_ids)

        assert result.valid is True
        assert result.quotes == []
        assert result.invalid_quotes == []
        assert result.unbound_evidence_refs == []

    def test_empty_string_returns_valid_true(self):
        """Leere Section → quotes=[], valid=True."""
        result = validate_quote_anchors("", {}, [])

        assert result.valid is True
        assert result.quotes == []


# ---------------------------------------------------------------------------
# 9. EvidenceMapModel-Instanz als evidence_map → funktioniert auch
# ---------------------------------------------------------------------------

class TestEvidenceMapModelInstance:
    def test_accepts_evidence_map_model_instance(self):
        """validate_quote_anchors() akzeptiert auch EvidenceMapModel-Objekte."""
        from app.contracts.report_contract import EvidenceMapModel, EvidenceRecordModel, EvidenceType

        evidence_id = "ev_00000000000000000000000000000001"
        item = EvidenceRecordModel(
            evidence_id=evidence_id,
            producer_key="quote-anchor-fixture",
            type=EvidenceType.graph_fact,
            source="test-src",
            snippet="Test-Snippet",
            source_id_anchor="ev_map_001",
        )
        em = EvidenceMapModel(
            report_id="r1",
            simulation_id="s1",
            evidence_index={evidence_id: item},
            global_evidence_refs=[evidence_id],
            sections=[],
        )

        tag = _make_quote_tag(persona_id="persona_01", seed_anchor="ev_map_001")
        result = validate_quote_anchors(tag, em, ["persona_01"])

        assert result.valid is True

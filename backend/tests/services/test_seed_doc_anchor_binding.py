"""Issue #1249 — ``seed_doc:``-Anker umgingen die Bindungsprüfung vollständig.

Die Validierung prüfte einen Anker nur dann gegen die bekannten Anker, wenn er
das ``seed_doc:``-Präfix **nicht** trug:

    # seed_doc:-Prefix ist immer akzeptiert (opaque Referenz)
    if not seed_anchor.startswith(_SEED_DOC_PREFIX):
        if seed_anchor not in known_anchors:
            …unbound_evidence_refs…

Ein ``ev_``-Anker ohne Bindung wurde als ``unbound_evidence_refs`` sichtbar,
``seed_doc:beliebig`` niemals.

Das Modell wählte in den beobachteten Läufen exakt diesen einen ungeprüften
Pfad — mit dem Wert, den der Prompt ihm vorgab. In ``section_01.md`` eines
Laufs trugen alle 8 Zitate von 7 verschiedenen Personas den Anker
``seed_doc:interview_transcript_07``; ein Dokument dieses Namens existierte im
Lauf nicht. Ein stärkeres Modell konstruierte stattdessen pro Persona einen
individuell klingenden Anker (``seed_doc:interview_<name>``), der ebenfalls
auf nichts verweist — dann sieht jedes Zitat einzeln belegt aus.

**Eine eigene Auflösungsquelle braucht es dafür nicht:** Echte Seed-Anker haben
nach ADR-0013 die Form ``seed_doc:<document_id>#chunk:<chunk_id>`` und stehen
als ``source_id_anchor`` bereits in ``known_anchors``.

**Politik (Sign-off 2026-08-11):** führen wie einen ungebundenen ``ev_``-Anker
— sichtbar als ``unbound_evidence_refs``, ohne das Zitat hart zu verwerfen.
Ein real existierendes, aber aus technischen Gründen nicht indiziertes
Dokument kostet damit Sichtbarkeit, keinen Inhalt.
"""

from __future__ import annotations

from types import SimpleNamespace

from app.services.report_agent.evidence import validate_quote_anchors

_PERSONAS = ["persona_01", "persona_02"]

#: Ein realer Seed-Anker nach ADR-0013 — Dokument-ID plus Chunk.
_REAL_ANCHOR = "seed_doc:doc_a1b2c3#chunk:7"

_BOUND_EV_ID = "ev_" + "0" * 32

#: Objektform der EvidenceMap — ``_extract_known_anchors`` liest hier die
#: ``source_id_anchor``-Attribute, ohne den Persistenz-Normalisierer zu
#: durchlaufen. Der Prüfgegenstand ist die Ankerbindung, nicht das Ladeformat.
_EVIDENCE_MAP = SimpleNamespace(
    evidence_index={
        _BOUND_EV_ID: SimpleNamespace(source_id_anchor=_REAL_ANCHOR),
    }
)


def _section(*quotes: tuple[str, str]) -> str:
    tags = "\n".join(
        f'<simulated_quote persona_id="{pid}" seed_anchor="{anchor}">'
        f"Aussage von {pid}.</simulated_quote>"
        for pid, anchor in quotes
    )
    return f"# Abschnitt\n\n{tags}\n"


def test_erfundener_seed_doc_anker_wird_als_ungebunden_gefuehrt():
    """RED ohne den Fix: der Anker passiert die Prüfung ohne jede Spur."""
    result = validate_quote_anchors(
        _section(("persona_01", "seed_doc:interview_transcript_07")),
        _EVIDENCE_MAP,
        _PERSONAS,
    )

    assert result.unbound_evidence_refs == ["seed_doc:interview_transcript_07"], (
        "Ein nicht auflösbarer seed_doc:-Anker muss sichtbar werden"
    )


def test_der_beobachtete_fall_acht_zitate_ein_erfundener_anker():
    """Alle acht Zitate einer Section trugen denselben Prompt-Beispielwert."""
    quotes = tuple(
        (f"persona_{i % 2 + 1:02d}", "seed_doc:interview_transcript_07")
        for i in range(8)
    )
    result = validate_quote_anchors(_section(*quotes), _EVIDENCE_MAP, _PERSONAS)

    assert len(result.unbound_evidence_refs) == 8


def test_individuell_erfundene_anker_werden_einzeln_sichtbar():
    """Die schlimmere Variante: pro Persona ein eigener, wertloser Anker.

    Konstante Anker fallen beim Lesen auf. Individuelle nicht — jedes Zitat
    sieht einzeln belegt aus.
    """
    result = validate_quote_anchors(
        _section(
            ("persona_01", "seed_doc:interview_nora_schulz"),
            ("persona_02", "seed_doc:interview_tobias_bauer"),
        ),
        _EVIDENCE_MAP,
        _PERSONAS,
    )

    assert sorted(result.unbound_evidence_refs) == [
        "seed_doc:interview_nora_schulz",
        "seed_doc:interview_tobias_bauer",
    ]


def test_realer_seed_doc_anker_bleibt_gueltig():
    """Gegenprobe: ein Anker, der im Index steht, ist gebunden."""
    result = validate_quote_anchors(
        _section(("persona_01", _REAL_ANCHOR)), _EVIDENCE_MAP, _PERSONAS
    )

    assert result.unbound_evidence_refs == []
    assert result.valid is True


def test_zitat_bleibt_gueltig_und_wird_nicht_verworfen():
    """Die gewählte Politik verwirft nicht — der Inhalt bleibt erhalten."""
    result = validate_quote_anchors(
        _section(("persona_01", "seed_doc:erfunden")), _EVIDENCE_MAP, _PERSONAS
    )

    assert result.invalid_quotes == []
    assert len(result.quotes) == 1
    assert result.quotes[0]["persona_id"] == "persona_01"


def test_ev_anker_verhalten_ist_unveraendert():
    """Die bestehende Behandlung von ``ev_``-Ankern darf sich nicht ändern."""
    bound = validate_quote_anchors(
        _section(("persona_01", _BOUND_EV_ID)), _EVIDENCE_MAP, _PERSONAS
    )
    assert bound.unbound_evidence_refs == []

    unbound = validate_quote_anchors(
        _section(("persona_01", "ev_" + "f" * 32)), _EVIDENCE_MAP, _PERSONAS
    )
    assert unbound.unbound_evidence_refs == ["ev_" + "f" * 32]


def test_fehlender_anker_bleibt_ein_ungueltiges_zitat():
    """Ein *fehlender* Anker ist weiterhin ein harter Fehler, kein ungebundener."""
    section = (
        '# Abschnitt\n\n<simulated_quote persona_id="persona_01">'
        "Ohne Anker.</simulated_quote>\n"
    )
    result = validate_quote_anchors(section, _EVIDENCE_MAP, _PERSONAS)

    assert result.valid is False
    assert result.unbound_evidence_refs == []
    assert "missing seed_anchor" in result.invalid_quotes[0]["reason"]


def test_section_ohne_zitate_bleibt_gueltig():
    result = validate_quote_anchors("# Abschnitt ohne Zitate\n", _EVIDENCE_MAP, _PERSONAS)

    assert result.valid is True
    assert result.unbound_evidence_refs == []

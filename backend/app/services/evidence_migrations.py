"""Evidence-Map-Migration v1 -> v2 und P2.1-Anker-Migration.

Sub-Slice 02a — Refs #107.
Sub-Slice P2.1 — Evidence-Anker-Pflicht für medium/high-Claims.

- ``migrate_v1_to_v2`` hebt persistierte Evidence-Maps auf schema_version=2.
- ``migrate_legacy_claims_to_anchored`` entfernt orphan Claims VOR Validator,
  damit Bestands-evidence-map.json nicht beim Reload an
  ``ReportClaimModel.non_low_claims_need_evidence`` scheitern.
- ``migrate_evidence_map_v2_to_v3`` trennt kanonische Evidence-Records von
  Claim-Bindings und hebt persistierte Evidence-Maps auf schema_version=3.

Kein Report-Container-Aufbau mehr: ``migrate_v2_to_v3`` ist entfallen (siehe
``docs/decisions/0005-keine-v2-report-migration.md``). ReportV3 entsteht
ausschliesslich in ``report_agent/manager.py::build_report_v3``; persistierte
ReportV3-Dateien hebt ``report_agent/storage.py::_upgrade_report_v3_payload``
auf Schema 4.
"""

from __future__ import annotations

import re
from typing import Any, Optional

from .evidence_identity import build_evidence_id

LEGACY_SCHEMA_VERSION = 2
CURRENT_SCHEMA_VERSION = 3

# Confidence-Labels, die einen Evidence-Anker erfordern (P2.1).
_ANCHOR_REQUIRED_LABELS = frozenset({"medium", "high", "verified"})

# Section-Titel-Schlüsselwörter für FrictionPoints und TrustSignals.
_FRICTION_KEYWORDS = frozenset({"reibungspunkt", "reibungs", "friction", "hindernis", "barriere"})
_TRUST_KEYWORDS = frozenset({"vertrauenssignal", "vertrauens", "trust", "cialdini"})

# Signal-Type-Fallback für TrustSignals aus Section-Claims.
_DEFAULT_TRUST_SIGNAL_TYPE = "authority"

# Issue #986: Erkennt vorhandene ``gap_<n>``-IDs, um bei der Neuvergabe in
# ``migrate_legacy_claims_to_anchored`` Kollisionen mit lückenhaft nummerierten
# Bestands-Gaps (z. B. gap_01, gap_03) zu vermeiden.
_GAP_ID_SUFFIX_RE = re.compile(r"^gap_(\d+)$")

# Erlaubte voice_register-Werte (gespiegelt aus report_v3.Persona).
_VALID_VOICE_REGISTERS = frozenset({"formal-de", "neutral-de", "technical-de", "skeptisch-de"})
_DEFAULT_VOICE_REGISTER = "neutral-de"


def migrate_v1_to_v2(raw: Optional[dict]) -> Optional[dict]:
    """Hebt eine persistierte Evidence-Map auf schema_version=2.

    - ``None`` wird unverändert zurückgegeben.
    - Mutiert das übergebene Dict in-place und gibt es zurück, damit Caller wahlweise
      Rückgabewert oder Original verwenden können.
    - Entfernt ``schema_version`` aus Section-Einträgen (#1037): Die Version
      gehört an die Map, nicht an jede Section — ``ReportSectionModel`` ist
      strict (``extra="forbid"``) und kennt das Feld nicht. Bis #1037 schrieb
      diese Migration den Schlüssel selbst in jede Section und machte damit
      genau die Maps unlesbar, die sie retten sollte. Die Bereinigung läuft
      deshalb auch für Maps, die bereits auf v2 stehen: über den in-memory
      Migrationspfad (report_agent/workflow) können vergiftete v2-Bestände
      persistiert worden sein, für die der frühere Early-Return die Heilung
      übersprungen hätte.
    """
    if raw is None:
        return None
    sections = raw.get("sections") or []
    for section in sections:
        if isinstance(section, dict):
            section.pop("schema_version", None)
    if raw.get("schema_version") in {LEGACY_SCHEMA_VERSION, CURRENT_SCHEMA_VERSION}:
        return raw

    raw["schema_version"] = LEGACY_SCHEMA_VERSION
    return raw


def migrate_legacy_claims_to_anchored(raw: Optional[dict]) -> Optional[dict]:
    """P2.1: Überführt Claims ohne Evidence-Anker in data_gaps.

    Verhindert, dass alte ``evidence-map.json``-Dateien beim Reload durch
    den ``ReportClaimModel``-Validator (``non_low_claims_need_evidence``)
    abgelehnt werden.

    Regeln (spiegeln ``_finalize_section_claims`` in agent.py):
    - Claim ohne Evidence + ``confidence_label`` in {medium, high, verified}
      → entfernen aus ``claims[]``, anhängen an ``data_gaps[]`` mit
      ``gap_reason="no_evidence_bound"``.
    - Claim ohne Evidence + ``confidence_label=low`` oder kein Label
      → unverändert lassen (Validator erlaubt das).
    - Hypotheses- und Data-Gaps-Felder werden initialisiert, falls sie
      in der Section noch nicht existieren.

    Gibt ``None`` zurück, wenn ``raw`` None ist. Mutiert das übergebene Dict.
    """
    if raw is None:
        return None

    sections = raw.get("sections") or []
    for section in sections:
        if not isinstance(section, dict):
            continue

        section.setdefault("hypotheses", [])
        section.setdefault("data_gaps", [])

        # Issue #986: Bestands-gap_ids der Section einsammeln, damit neue IDs
        # weder mit lückenhaft nummerierten Bestands-Gaps (gap_01, gap_03)
        # noch untereinander kollidieren. Malformed/nicht-dict-Einträge
        # werden toleriert (kein Crash), einfach ignoriert.
        existing_gap_ids: set[str] = set()
        next_gap_index = 1
        for existing_gap in section["data_gaps"]:
            if not isinstance(existing_gap, dict):
                continue
            gap_id = existing_gap.get("gap_id")
            if gap_id is None:
                continue
            gap_id = str(gap_id)
            existing_gap_ids.add(gap_id)
            match = _GAP_ID_SUFFIX_RE.match(gap_id)
            if match:
                next_gap_index = max(next_gap_index, int(match.group(1)) + 1)

        claims = section.get("claims") or []
        surviving_claims = []

        for claim in claims:
            if not isinstance(claim, dict):
                surviving_claims.append(claim)
                continue

            evidence = claim.get("evidence") or []
            label = str(claim.get("confidence_label") or "").lower()

            if not evidence and label in _ANCHOR_REQUIRED_LABELS:
                new_gap_id = f"gap_{next_gap_index:02d}"
                while new_gap_id in existing_gap_ids:
                    next_gap_index += 1
                    new_gap_id = f"gap_{next_gap_index:02d}"
                existing_gap_ids.add(new_gap_id)
                next_gap_index += 1

                claim_text = (
                    str(claim.get("claim_text") or claim.get("claim") or "").strip()
                    or "Legacy claim ohne Evidence-Text."
                )[:1000]
                section["data_gaps"].append({
                    "gap_id": new_gap_id,
                    "claim_text": claim_text,
                    "gap_reason": "no_evidence_bound",
                    "suggested_fix": "Evidence per Graph- oder Agent-Tool nachreichen.",
                })
            else:
                surviving_claims.append(claim)

        section["claims"] = surviving_claims

    return raw


def migrate_medium_seed_only_claims_to_low(raw: Optional[dict]) -> Optional[dict]:
    """Issue #963: Stuft medium-Claims ohne agent-grounded Evidence auf low ab.

    Seit PR #961 verlangt ``ReportClaimModel.agent_grounded_for_medium`` für
    das ``medium``-Label mind. 1 ``agent_quote`` (mit nicht-leerem
    ``quote``-Feld) UND mind. 1 ``seed_corpus``. Persistierte Maps, die vor
    dieser Änderung erzeugt wurden und medium-Claims nur auf
    ``seed_corpus``/``graph_relation``-Evidence stützen, würden sonst beim
    Laden (``EvidenceMapModel.model_validate``) mit HTTP 422 brechen.

    Regeln:
    - Claim mit ``confidence_label == "medium"`` (case-insensitive) ohne
      agent-grounded Evidence (``has_agent_grounded_evidence``) → Label
      wird ``"low"``.
    - ``high``/``verified``-Claims werden nicht angefasst (separates Thema).
    - Idempotent: bereits ``low`` gelabelte Claims bleiben unverändert.

    Gibt ``None`` zurück, wenn ``raw`` None ist. Mutiert das übergebene Dict.
    """
    if raw is None:
        return None

    # Lazy-Import: ``report_agent.schemas`` importiert selbst aus diesem
    # Modul (``CURRENT_SCHEMA_VERSION``, ``migrate_v1_to_v2``) — ein
    # Modul-Level-Import von ``report_agent.evidence`` wäre zirkulär.
    from .report_agent.evidence import has_agent_grounded_evidence

    sections = raw.get("sections") or []
    for section in sections:
        if not isinstance(section, dict):
            continue
        for claim in section.get("claims") or []:
            if not isinstance(claim, dict):
                continue
            label = str(claim.get("confidence_label") or "").lower()
            if label != "medium":
                continue
            evidence = claim.get("evidence") or []
            # Ab schema_version 3 tragen die Claim-Einträge nur noch die
            # Referenz; source_kind und quote stehen kanonisch am Record.
            # Ohne den Index läse die Prüfung leere Felder und stufte jeden
            # medium-Claim ab (Issue #1154).
            if not has_agent_grounded_evidence(
                evidence, evidence_index=raw.get("evidence_index") or {}
            ):
                claim["confidence_label"] = "low"

    return raw


# Binding-Stärke für Merge-Kollisionen (Spiegelung von
# ``report_agent.agent._binding_strength``). Beide Stellen nutzen dieselbe
# strongest-binding-Policy; eine Konsolidierung in ein gemeinsames Modul
# steht als Folgearbeit aus (siehe #1277-6).
_ENTAILMENT_RANK: dict[str, int] = {
    "SUPPORTED": 3,
    "RELATED_ONLY": 2,
    "INSUFFICIENT": 1,
    "CONTRADICTED": 0,
}


def _binding_strength(binding: dict[str, Any]) -> tuple[int, float]:
    """Entailment-Rang, Tie-Break über ``match_score`` — höhere Werte gewinnen."""
    rank = _ENTAILMENT_RANK.get(str(binding.get("entailment") or ""), 0)
    return (rank, float(binding.get("match_score") or 0.0))


def _remap_and_merge_bindings(
    bindings: list[Any], remap: dict[str, str]
) -> list[dict[str, Any]]:
    """Re-Keyt Bindungen und führt Kollisionen zur stärksten Bindung zusammen.

    Zwei Bindungen, die nach dem Re-Key auf dieselbe Quelle zeigen, sind eine
    Bindung — sonst zählt die Confidence-Berechnung dieselbe Quelle doppelt.
    Bei Kollision gewinnt die stärkere Bindung (Entailment-Rang, Tie-Break über
    ``match_score``), nicht die erste — eine schwächere ``RELATED_ONLY``-Bindung
    darf eine stärkere ``SUPPORTED``-Bindung nicht still verdrängen (#1277-6).
    """
    merged: dict[str, Any] = {}
    for binding in bindings:
        if not isinstance(binding, dict):
            continue
        binding_id = str(binding.get("evidence_id") or "")
        target = remap.get(binding_id, binding_id)
        binding["evidence_id"] = target
        existing = merged.get(target)
        if existing is None or _binding_strength(binding) > _binding_strength(existing):
            merged[target] = binding
    return list(merged.values())


def strip_seed_doc_anchor_from_agent_quote_records(raw: Optional[dict]) -> Optional[dict]:
    """Issue #1300 (Review-Finding Codex, P1): Bestandsschutz fuer die Producer-
    Boundary-Bereinigung in ``report_agent.evidence.register_evidence_record``.

    Diese entfernt einen erfundenen ``seed_doc:``-Anker auf Interview-Evidence
    nur beim NEUEN Schreiben. Vor dieser Aenderung persistierte Reports mit der
    Kombination ``source_kind=agent_quote`` + ``seed_doc:``-Anker liegen mit
    genau dieser Kombination auf Platte — ``EvidenceRecordModel.
    agent_quote_rejects_seed_doc_anchor`` lehnt sie beim naechsten Lesen mit
    einem harten ``ValidationError`` ab. Ohne diese Migration wuerde
    ``GET /api/report/<id>/evidence`` fuer jeden betroffenen Bestands-Report
    mit HTTP 422 antworten und JSON/ZIP/CSV-Export die Evidence-Map stumm
    auslassen (vgl. die Begruendung fuer ``demote_unanchored_seed_corpus_records``
    oben — derselbe Fehlermodus, anderer Validator).

    Im Unterschied zu ``demote_unanchored_seed_corpus_records`` bleibt
    ``source_kind`` unveraendert (``agent_quote`` bleibt ``agent_quote``) —
    ``build_evidence_id`` haengt nur an ``scope_id``, ``source_kind`` und
    ``producer_key``, keiner davon aendert sich hier. Die ``evidence_id``
    bleibt stabil, ein Re-Key wie dort ist nicht noetig.

    Idempotent: ein Record ohne ``seed_doc:``-Anker bleibt unangetastet.
    Mutiert das uebergebene Dict; gibt ``None`` zurueck, wenn ``raw`` None ist.
    """
    if raw is None:
        return None

    from ..contracts.report_contract import SEED_DOC_ANCHOR_PREFIX

    evidence_index = raw.get("evidence_index")
    if not isinstance(evidence_index, dict) or not evidence_index:
        return raw

    for record in evidence_index.values():
        if not isinstance(record, dict):
            continue
        if (
            record.get("source_kind") == "agent_quote"
            and str(record.get("source_id_anchor") or "").startswith(SEED_DOC_ANCHOR_PREFIX)
        ):
            record.pop("source_id_anchor", None)

    return raw


def demote_unanchored_seed_corpus_records(
    raw: Optional[dict],
    *,
    remap_out: Optional[dict[str, str]] = None,
) -> Optional[dict]:
    """ADR-0013 / Issue #1154: ``seed_corpus`` ohne verifizierten Dokumentanker.

    Ein Evidence-Record gilt nur dann als Dokumentfakt, wenn er auf eine
    konkrete Stelle im Ausgangsdokument zeigt
    (``seed_doc:<document_id>#chunk:<chunk_id>``, siehe
    ``build_seed_document_anchor``). Vor #1154 war ``seed_corpus`` der Default
    für alles, was aus dem Graphen kam — solche Records behaupten einen
    Dokumentbeleg, den niemand nachschlagen kann. Beim Laden verlieren sie
    ihren Seed-Status und werden zu ``graph_relation``.

    **Warum das ein Identitätswechsel ist, kein Label-Update:**
    ``build_evidence_id(scope_id, source_kind, producer_key)`` nimmt
    ``source_kind`` in den Hash. Bliebe die alte ``evidence_id`` stehen, würde
    derselbe Beleg beim nächsten Schreiben über
    ``register_evidence_record`` unter einer zweiten ID landen — eine
    gespaltene Identität für dieselbe Quelle. Deshalb wird umgeschlüsselt.

    Das Umschlüsseln ist genau dann gefährlich, wenn die Referenzen
    zurückbleiben: ``EvidenceMapModel.validate_evidence_cross_references``
    prüft ``global_evidence_refs`` und jede Claim-Bindung gegen die Schlüssel
    des ``evidence_index`` und wirft sonst — das wäre der HTTP 422, den diese
    Migration verhindern soll. Index-Schlüssel, ``evidence_id`` und alle
    Referenzen wandern deshalb in einem Durchgang.

    (Der Validator prüft die ID *nicht* gegen den Hash. Ein reines Umschreiben
    von ``source_kind`` würde also nicht sofort brechen — es hinterließe nur
    die gespaltene Identität oben. Der Grund für das Re-Key ist Konsistenz,
    nicht das Abwenden eines unmittelbaren 422.)

    Kollidiert die neue ID mit einem bereits vorhandenen Record, gewinnt der
    vorhandene und die Referenzen werden zusammengeführt: derselbe
    ``producer_key`` in derselben Gattung ist dieselbe Quelle.

    ``remap_out`` nimmt die Zuordnung ``alte_id -> neue_id`` entgegen. Wer die
    Map nicht nur lädt, sondern nebenher noch Referenzen im Speicher hält —
    ``ReportAgent`` puffert die Evidence des laufenden Abschnitts —, muss sie
    im selben Zug nachziehen. Ohne das zeigen die als Nächstes gebauten Claims
    auf die alten Schlüssel, und der Cross-Reference-Validator wirft.

    Idempotent: ein bereits abgestufter Record trägt ``graph_relation`` und
    wird nicht erneut angefasst. Mutiert das übergebene Dict; gibt ``None``
    zurück, wenn ``raw`` None ist.
    """
    if raw is None:
        return None

    # Lazy-Import: ``report_agent.evidence`` importiert aus diesem Modul.
    from .report_agent.evidence import is_verified_seed_document_anchor

    evidence_index = raw.get("evidence_index")
    if not isinstance(evidence_index, dict) or not evidence_index:
        return raw

    scope_id = str(raw.get("simulation_id") or raw.get("report_id") or "legacy")
    rebuilt: dict[str, Any] = {}
    remap: dict[str, str] = {}

    for evidence_id, record in evidence_index.items():
        if (
            not isinstance(record, dict)
            or record.get("source_kind") != "seed_corpus"
            or is_verified_seed_document_anchor(record.get("source_id_anchor"))
        ):
            rebuilt.setdefault(evidence_id, record)
            continue

        demoted = dict(record)
        demoted["source_kind"] = "graph_relation"
        if demoted.get("type") == "seed_document":
            # Ohne Anker ist es kein Dokumentfakt — der Typ darf das nicht
            # weiter behaupten.
            demoted["type"] = "graph_fact"

        producer_key = str(demoted.get("producer_key") or "").strip()
        if not producer_key:
            # Ohne producer_key ist keine kanonische ID berechenbar. Der
            # Seed-Status fällt trotzdem: lieber ein ehrlich abgestufter
            # Record unter alter ID als ein unbelegter Dokumentfakt.
            demoted["evidence_id"] = evidence_id
            rebuilt[evidence_id] = demoted
            continue

        new_id = build_evidence_id(scope_id, "graph_relation", producer_key)
        remap[evidence_id] = new_id
        if new_id in rebuilt:
            continue
        demoted["evidence_id"] = new_id
        rebuilt[new_id] = demoted

    if remap_out is not None:
        remap_out.update(remap)

    if not remap:
        raw["evidence_index"] = rebuilt
        return raw

    raw["evidence_index"] = rebuilt

    raw["global_evidence_refs"] = list(dict.fromkeys(
        remap.get(str(ref), str(ref)) for ref in raw.get("global_evidence_refs") or []
    ))

    for section in raw.get("sections") or []:
        if not isinstance(section, dict):
            continue
        for claim in section.get("claims") or []:
            if not isinstance(claim, dict):
                continue
            bindings = claim.get("evidence")
            if isinstance(bindings, list):
                claim["evidence"] = _remap_and_merge_bindings(bindings, remap)
            legacy_refs = claim.get("evidence_refs")
            if isinstance(legacy_refs, list):
                claim["evidence_refs"] = list(dict.fromkeys(
                    remap.get(str(ref), str(ref)) for ref in legacy_refs
                ))

    return raw


def normalize_persisted_evidence_map(
    raw: Optional[dict],
    *,
    remap_out: Optional[dict[str, str]] = None,
) -> Optional[dict]:
    """Die kanonische Normalisierung einer persistierten ``evidence-map.json``.

    Jeder produktive Pfad, der eine Evidence-Map von der Platte liest, ruft
    **diese** Funktion — nicht die Einzelschritte. Aufrufer sind der Lese-Pfad
    ``GET /api/report/<id>/evidence`` (``api/report.py``), der JSON-Export
    ``GET /api/report/<id>/export?format=json``
    (``report_export.py::build_export_envelope``, validiert zusaetzlich gegen
    ``EvidenceMapModel``) sowie ZIP- und CSV-Export
    (``report_export.py::ReportExportService._normalized_evidence_map``,
    Issue #1036), ueber die ``build_zip_bundle``, ``stream_zip_bundle`` und
    ``build_csv_export`` laufen.

    Der Export rief bis Issue #987 nur ``migrate_v1_to_v2`` und fing die
    anschliessende ``ValidationError`` mit einer ``logger.warning`` ab — die
    gesamte Evidence-Map fiel dann aus dem Envelope, waehrend die Antwort
    HTTP 200 blieb. Zwei Pfade, zwei Reihenfolgen, ein stiller Datenverlust.
    Deshalb liegt die Reihenfolge jetzt an genau einer Stelle.

    Fuer Legacy-Maps ist die Reihenfolge bindend (Issue #968):

    1. ``migrate_v1_to_v2``
    2. ``migrate_legacy_claims_to_anchored``
    3. ``migrate_medium_seed_only_claims_to_low`` (Issue #963)
    4. Aufrufer validiert gegen ``EvidenceMapModel``

    Begruendung: ``migrate_legacy_claims_to_anchored`` haengt Claims, die GAR
    KEINE Evidence tragen, zuerst nach ``data_gaps`` um. Danach sieht die
    medium-Logik aus #963 nur noch Claims mit tatsaechlich vorhandener
    Evidence und prueft keine bereits umgehaengten Claims ein zweites Mal.

    Die umgekehrte Reihenfolge ist nicht bloss ineffizient, sie liefert ein
    ANDERES Ergebnis: ``has_agent_grounded_evidence([])`` ist False, also stuft
    #963 einen orphan medium-Claim zuerst auf ``low`` ab. Danach greift
    ``_ANCHOR_REQUIRED_LABELS`` nicht mehr (``low`` ist dort nicht enthalten)
    und der Claim bleibt dauerhaft als evidenzlose Aussage in ``claims[]``
    stehen, statt als Datenluecke ausgewiesen zu werden — das unterlaeuft die
    Zusage, dass jede Aussage im Report belegt ist. Getauscht ergibt dieselbe
    Map ``claims=[claim_90:low], data_gaps=[]`` statt
    ``claims=[], data_gaps=[1]``.

    Waechter dieser Ordnung sind
    ``tests/api/test_report_evidence_route.py::TestReportEvidenceRouteOrphanClaims
    ::test_orphan_medium_claim_becomes_data_gap`` (Ordnung) und
    ``tests/api/test_report_export_evidence_parity.py::TestExportAndReadPathAgree``
    (Gleichheit beider Pfade).

    Mutiert das uebergebene Dict wie die Einzelschritte und gibt ``None``
    zurueck, wenn ``raw`` None ist.
    """
    if raw is None:
        return None
    if raw.get("schema_version") == CURRENT_SCHEMA_VERSION:
        if "global_evidence" in raw:
            scope_id = str(
                raw.get("simulation_id") or raw.get("report_id") or "legacy"
            )
            evidence_index = raw.setdefault("evidence_index", {})
            global_refs = list(raw.get("global_evidence_refs") or [])
            for item in raw.pop("global_evidence") or []:
                if not isinstance(item, dict):
                    continue
                resolved = _legacy_item_to_record_and_binding(
                    item, scope_id=scope_id
                )
                if resolved is None:
                    continue
                record, _ = resolved
                evidence_id = record["evidence_id"]
                evidence_index.setdefault(evidence_id, record)
                global_refs.append(evidence_id)
            raw["global_evidence_refs"] = list(dict.fromkeys(global_refs))
        # Issue #1154, Schritte 5 und 6: erst den Seed-Status prüfen, dann die
        # Claim-Labels. Ein Record, der hier seinen Dokumentbeleg verliert,
        # kann einen medium-Claim tragen, der danach nicht mehr agent-grounded
        # ist — der muss im selben Durchgang auf low fallen, sonst scheitert
        # das Laden am medium-Validator (HTTP 422 statt ehrlicher Abstufung).
        # Issue #1300: der seed_doc-Anker-Strip auf agent_quote-Records ist von
        # der Seed-Corpus-Abstufung unabhaengig (disjunkte source_kind-Werte,
        # keine ID-Aenderung) — Reihenfolge relativ zu den beiden Schritten
        # unten ist beliebig, muss aber vor der Contract-Validierung im
        # Aufrufer liegen.
        return migrate_medium_seed_only_claims_to_low(
            demote_unanchored_seed_corpus_records(
                strip_seed_doc_anchor_from_agent_quote_records(raw), remap_out=remap_out
            )
        )
    legacy = migrate_medium_seed_only_claims_to_low(
        migrate_legacy_claims_to_anchored(migrate_v1_to_v2(raw))
    )
    # Der Seed-Status hängt an den Records, die erst v2→v3 entstehen — der
    # Downgrade läuft deshalb nach der Aufteilung. Die anschließende
    # medium-Prüfung sieht dann Records statt Legacy-Items.
    return migrate_medium_seed_only_claims_to_low(
        demote_unanchored_seed_corpus_records(
            strip_seed_doc_anchor_from_agent_quote_records(
                migrate_evidence_map_v2_to_v3(legacy)
            ),
            remap_out=remap_out,
        )
    )


_RECORD_FIELDS = frozenset({
    "type",
    "source",
    "snippet",
    "value",
    "tool_name",
    "query",
    "raw",
    "agent_log_ref",
    "quote",
    "source_id_anchor",
    "sentiment_score",
    "source_kind",
    "source_model",
    "persona_stakeholder_group",
    # Issue #1248: Rollenfamilien-Label. Ohne diesen Eintrag faellt es beim
    # Migrieren aelterer Artefakte still weg und der Cross-Stakeholder-Anker
    # rechnete wieder mit Berufstiteln.
    "persona_role_family",
})
_BINDING_FIELDS = frozenset({
    "match_score",
    "retrieval_score",
    "entailment",
    "entailment_reason",
    "supports_claim",
    "contradicts_claim",
})


def _legacy_item_to_record_and_binding(
    item: dict[str, Any],
    *,
    scope_id: str,
) -> tuple[dict[str, Any], dict[str, Any]] | None:
    """Konvertiert nur Legacy-Items mit explizitem Producer-Schluessel."""

    anchor = str(item.get("source_id_anchor") or "").strip()
    producer_key = str(item.get("producer_key") or "").strip()
    if not producer_key:
        # Ein vorhandener, nicht vom LLM-Sonderfall ``seed_doc`` stammender
        # Hartanker erlaubt eine eindeutige Legacy-Zuordnung. Freie ``source``-
        # Werte wie ``report_tool`` bleiben bewusst unresolved.
        if anchor and not anchor.startswith("seed_doc:"):
            producer_key = f"legacy-anchor:{anchor}"
    if not producer_key:
        return None
    source_kind = str(item.get("source_kind") or "").strip()
    if not source_kind:
        source_kind = "graph_relation" if anchor.startswith("kg:") else "inferred"
    evidence_id = build_evidence_id(scope_id, source_kind, producer_key)
    record = {key: item[key] for key in _RECORD_FIELDS if key in item}
    if record.get("type") == "graph_node":
        record["type"] = "graph_fact"
    if not str(record.get("source") or "").strip():
        record["source"] = anchor or producer_key
    if not str(record.get("snippet") or "").strip():
        record["snippet"] = "[legacy evidence snippet missing]"
    record.update({
        "evidence_id": evidence_id,
        "producer_key": producer_key,
        "source_kind": source_kind,
    })
    binding = {key: item[key] for key in _BINDING_FIELDS if key in item}
    binding["evidence_id"] = evidence_id
    return record, binding


def _next_legacy_hypothesis_id(section: dict[str, Any]) -> str:
    used = {
        str(item.get("hypothesis_id"))
        for slot in ("hypotheses", "hypotheses_appendix")
        for item in section.get(slot) or []
        if isinstance(item, dict) and item.get("hypothesis_id")
    }
    index = 1
    while f"hypothesis_{index:02d}" in used:
        index += 1
    return f"hypothesis_{index:02d}"


def migrate_evidence_map_v2_to_v3(raw: Optional[dict]) -> Optional[dict]:
    """Hebt eine normalisierte Legacy-EvidenceMap auf den ID-Vertrag v3."""

    if raw is None:
        return None
    if raw.get("schema_version") == CURRENT_SCHEMA_VERSION:
        return raw

    scope_id = str(raw.get("simulation_id") or raw.get("report_id") or "").strip()
    evidence_index: dict[str, dict[str, Any]] = {}
    global_refs: list[str] = []
    for item in raw.get("global_evidence") or []:
        if not isinstance(item, dict):
            continue
        converted = _legacy_item_to_record_and_binding(item, scope_id=scope_id)
        if converted is None:
            continue
        record, _ = converted
        evidence_index[record["evidence_id"]] = record
        global_refs.append(record["evidence_id"])

    for section in raw.get("sections") or []:
        if not isinstance(section, dict):
            continue
        section.setdefault("hypotheses", [])
        surviving_claims: list[Any] = []
        for claim in section.get("claims") or []:
            if not isinstance(claim, dict):
                continue
            bindings: list[dict[str, Any]] = []
            unresolved = False
            for item in claim.get("evidence") or []:
                if not isinstance(item, dict):
                    unresolved = True
                    continue
                converted = _legacy_item_to_record_and_binding(item, scope_id=scope_id)
                if converted is None:
                    unresolved = True
                    continue
                record, binding = converted
                evidence_index[record["evidence_id"]] = record
                bindings.append(binding)
            if bindings:
                migrated_claim = dict(claim)
                migrated_claim["evidence"] = bindings
                surviving_claims.append(migrated_claim)
                continue
            if unresolved or claim.get("evidence"):
                claim_text = str(
                    claim.get("claim_text") or claim.get("claim") or ""
                ).strip()
                if len(claim_text) >= 8:
                    section["hypotheses"].append({
                        "hypothesis_id": _next_legacy_hypothesis_id(section),
                        "hypothesis_text": claim_text[:1000],
                        "rationale": (
                            "legacy_unresolved: Legacy-Evidence besitzt keinen "
                            "verifizierbaren producer_key."
                        ),
                        "suggested_evidence": [],
                    })
            else:
                surviving_claims.append(claim)
        section["claims"] = surviving_claims

    raw.pop("global_evidence", None)
    raw["schema_version"] = CURRENT_SCHEMA_VERSION
    raw["evidence_index"] = evidence_index
    raw["global_evidence_refs"] = list(dict.fromkeys(global_refs))
    return raw















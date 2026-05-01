# Slice A4 — Evidence-Layer ist bereits modelliert (Closes #49)

**Datum:** 2026-05-01
**Sprint:** v0.9.0 — Domain Cleanup
**Issue:** #49 (EPIC-07-ST-05) — Evidence-Layer explizit modellieren (p2)

## Befund

Issue #49 fordert: *„Evidenz-Tracking pro Report-Aussage explizit modellieren (welche Graph-Knoten/Kanten haben zur Aussage geführt). Vorbereitung für EPIC-15 Confidence Layer."*

Durch Issue #103 (S4a, S4b, S5, S6) und Issue #45 (Models extrahieren) ist der Evidence-Layer jetzt vollständig modelliert. Alle drei Stoßrichtungen aus #49 sind im Code abgebildet:

### Datenmodell explizit

`backend/app/models/report.py` (seit Slice A3 / Issue #45 extrahiert):

- **`EvidenceItem`** (Z. 86-127): `type`, `source`, `value`, `snippet`, `tool_name`, `query`, `raw`, `agent_log_ref`. Felder `tool_name` und `query` tracken explizit, welcher Retrieval-Tool-Aufruf zu welchem Graph-Bezug geführt hat.
- **`ReportClaim`** (Z. 130-160): Verknüpft Claim-Text mit `confidence_score`, `confidence_label` und `evidence: List[Dict]`. Pro Aussage steht jetzt strukturiert da, *worauf* sie sich stützt.

### Evidence-Binding pro Claim

`backend/app/services/evidence_binder.py` (Issue #103, S4a, 101 LOC):
- `bind_evidence_to_claim(claim_text, evidence_pool)` macht Cosine-Matching zwischen Claim-Text und Evidence-Snippets
- Liefert nur Evidence zurück, deren `match_score >= threshold` (Default 0.3)
- Ersetzt das frühere generische Pool-Pattern, das alle Claims auf denselben Evidence-Pool referenziert hat

### Audit-Trail vs Evidence getrennt

Issue #103 S5 (`23ac344 feat(report): split self-evidence into audit_trail`):
- `audit_trail` (in Report-Sections) hält Self-Evidence-Items wie `section_synthesis`, `model_generated_inference`
- `evidence` (in Claims) hält nur tool-basierte Evidence aus Graph/Web-Retrieval
- Damit ist die zentrale Kritik aus dem externen Review (`agora_json_evdence_review.md`) adressiert: keine selbstreferenzielle Belegliste mehr

### Confidence-Layer (Vorbereitung für EPIC-15)

`backend/app/services/confidence_calculator.py` (Issue #103, S6, 133 LOC):
- Formel: `0.40 × relevance + 0.25 × quality + 0.20 × specificity + 0.15 × consistency − penalty`
- Label-Mapping: `low` / `medium` / `high` / `verified` (verified gated auf min `match_score >= 0.85`)
- Genau die Vorarbeit, die Issue #49 als „Vorbereitung für EPIC-15 Confidence Layer" angekündigt hat

## Akzeptanzkriterien-Abgleich

| Forderung aus #49 | Status | Beleg |
|---|---|---|
| Evidence pro Report-Aussage explizit modelliert | ✓ | `models/report.py` `EvidenceItem` (8 Felder), `ReportClaim` (`evidence: List`) |
| Welche Graph-Knoten/Kanten haben zur Aussage geführt | ✓ | `EvidenceItem.tool_name` + `query` (zeigt auf Retrieval-Tool-Aufruf), `agent_log_ref` (Trace zur Tool-Antwort), Bind-Logik in `evidence_binder.py` |
| Vorbereitung EPIC-15 Confidence Layer | ✓ | `confidence_calculator.py` mit 4-Komponenten-Formel + Label-Gate |

## Tests

- `backend/tests/test_evidence_binder.py` — Cosine-Match, Threshold, leerer Pool
- `backend/tests/test_confidence_calculator.py` — alle vier Komponenten, Label-Mapping, verified-Gate
- `backend/tests/test_report_manager.py` — Konstruktion von `Report` + `ReportClaim` über Re-Export-Pfad

Alle als Teil der 517 grünen Backend-Tests.

## Konsequenz für v0.9.0

Issue #49 wird mit dieser Status-Doku geschlossen. Verbleibender v0.9.0-Backlog: **8 echte Issues** (EPIC-06 ×2: #42/#43; EPIC-07 ×3: #46/#47/#48; EPIC-08 ×3: #50/#51/#52).

## Folge-Slice

Slice A5 (Issue #46) — `ReportLogger` und `ReportConsoleLogger` (~270 LOC) aus `report_agent.py` in `services/report_logger.py` extrahieren. Re-Export-Pattern analog zu Slice A3.

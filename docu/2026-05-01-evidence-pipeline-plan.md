# Evidence-Pipeline v2 + Repo-Hygiene Sweep — Master-Plan

**Datum:** 2026-05-01
**Auslöser:** Zwei externe Reviews (`agora_json_evdence_review.md`, `agora_repo_review_neuer_stand.md`).
**Status:** Plan fixiert, S0 (Diagnose) gestartet.

## Zielbild

Der Report soll *belegt* aussehen, **weil er belegt ist**. Heute teilt er sich:

- generische Evidence-Pools über alle Claims hinweg,
- Self-Evidence (`section_synthesis`, `model_generated_inference`) in der Belegliste,
- Confidence-Scores ohne Berechnungsgrundlage (alles 0.95),
- Metriken `0/0/0/0` neben Action-Logs ausgewiesen,
- XSS-Lücke im Markdown-Renderer.

Der Plan baut die Belegschicht von vorne neu auf, behält die produktive Demo-Tauglichkeit und schließt den XSS-Punkt parallel.

## Slice-Sequenz

| ID | Slice | Aufwand | Akzeptanzkriterium |
|---|---|---|---|
| **S0** | Diagnose-Skript: existierende Sim-Runs gegen `NetworkAnalyticsService` recomputen, Diff dokumentieren | S | ✅ erledigt — `docu/2026-05-01-metric-snapshot-diagnose.md`. **Hauptbefund: Schema-Mismatch in `_extract_target_agent`** (siehe S2-pre) |
| **S1** | XSS-Fix `Step4Report.vue` — DOMPurify oder marked-Sanitize-Config | S | `<script>alert(1)</script>` im Markdown wird gestrippt, neuer Vitest-Test grün, `npm run check` grün |
| **S2-pre** | **(neu nach S0)** Schema-Fix `_extract_target_agent`: Vorab-Index `post_id → agent_id` + `comment_id → agent_id` aus `CREATE_POST`/`CREATE_COMMENT`-Actions; Resolver in `_iter_interactions` einhängen | M | Diagnose-Skript zeigt für ≥6/10 Runs Verdict `metrics_consistent` und `total_interactions > 0` |
| **S2a** | `network_analytics.py`: für die echten Broadcast-Only-Fälle Status-Flag `no_pairwise_interactions` statt 0 ausweisen; Snapshot bekommt `snapshot_id` + `calculated_at` | S | Wenn `interactions=[]` aber `actions ≠ []` → Status `no_pairwise_interactions`, kein Lügen-0 |
| **S2b** | Frontend zeigt „Metriken nicht verfügbar" statt 0/0/0/0 wenn Status `no_pairwise_interactions` | XS | Vitest-Test, kein 0er-Block bei leerem Snapshot |
| **S3a** | Claim-Filter: Markdown-Header & kurze Bold-Zeilen aus Evidence-Map raus (Regex-Filter im `report_agent`) | S | Bekannter Test-Set: Header-Strings tauchen nicht mehr als Claim auf |
| **S3b** | Claim-Atomisierung: Prompt-Update + Post-Filter — eine prüfbare Aussage je Claim | M | Stichprobe alter Reports re-rendert, Multi-Aussage-Claims werden gesplittet oder verworfen |
| **S4a** | Neuer `services/evidence_binder.py` mit Embedding-Cosine-Matching + `match_score` ≥ Threshold | M | Unit-Tests: Claim mit semantisch passender Evidence → match_score > 0.7; mit irrelevanter → < 0.3 |
| **S4b** | Binder im `report_agent._collect_simulation_evidence_items` verdrahten, globaler Pool nur Fallback (≤2), `schema_version: 2` | M | Bestehender Report re-generiert, jeder Claim hat ≤5 Evidence-Items mit `match_score`, Globaler Pool drinnen nur als Fallback markiert |
| **S5** | `model_generated_inference`/`section_synthesis` aus `evidence` raus → in neues Feld `audit_trail` | S | Schema-Test: kein `evidence`-Item mit verbotenen Typen, `audit_trail` enthält die Originale |
| **S6** | Confidence-Formel + Label-Mapping (`low`/`medium`/`high`/`verified`) | S | Bekannte Cases erzeugen erwartete Labels; `verified` nur bei direkter, claim-spezifischer Evidence |
| **R0** | Dev-Tooling: `scripts/dev-rebuild.sh` + `scripts/verify-deploy.sh` + npm-Aliases (`dev:rebuild`, `dev:rebuild:deps`, `dev:rebuild:full`, `dev:verify`) | XS | Container-Workflow ohne Issue-Tracking nötig, pure Helfer |
| **R3** | CI-Ruff-Scope = lokal (`app/ tests/`) | XS | `.github/workflows/ci.yml` deckt denselben Scope wie `npm run lint:backend` |
| **R4** | Compose: `image:`/`build:`/Kommentar konsistent | XS | Doku entspricht Realität, kein Lügen-Kommentar mehr |
| **R1** | CI: Vitest im Frontend-Job aktiv | XS | PR triggert Vitest, Frontend-Job zeigt Test-Counts |
| **R2** | Prod-Dockerfile-Target (multi-stage, gunicorn + gebautes Frontend) | M | `docker compose --profile prod up` startet ohne Vite-Dev-Server |

**Reihenfolge:** S0 → S1 → **S2-pre** → S2a → S2b → S3a → S3b → S4a → S4b → S5 → S6 → R3 → R4 → R1 → R2.

**Begründung:**

- S0 vor allem anderen, weil die Diagnose Reihenfolge und Annahmen für S2 konkretisiert.
- S1 ist Security-P0, unabhängig vom Rest, wandert deshalb hochpriorig hoch.
- S4 hängt an S3 (Binder ohne saubere Claims sinnlos), S6 hängt an S4 (Confidence-Formel ohne Match-Score sinnlos).
- R-Slices als Aufräum-Cluster ans Ende: R3/R4 sind 5-Minuten-Slices, R1/R2 brauchen Test-Infra-Erweiterung.

## Konventionen

- 1 Sub-Slice = 1 Commit + 1 Arbeitsprotokoll unter `docu/2026-05-01-<slice>-protokoll.md` (oder Folgedatum).
- `npm run check` muss vor jedem Commit grün sein.
- Issues werden **nachgezogen**: nach S0 entscheidet die Diagnose, ob die Reihenfolge stehen bleibt; danach wird ein Epic-Issue mit Sub-Issue-Liste angelegt.
- Lineares Git, keine Merges; Slice-Commits direkt auf `main` (Ein-Personen-Repo, FF-Style).

## Schema-Version 2 (Skizze, finalisiert in S4b)

```json
{
  "report_id": "report_x",
  "simulation_id": "sim_x",
  "schema_version": 2,
  "metrics": {
    "snapshot_id": "metrics_<sim>_<ts>",
    "calculated_at": "2026-05-01T18:30:00+02:00",
    "status": "ok|no_pairwise_interactions|stale",
    "total_agents": 18,
    "total_interactions": 42,
    "cluster_count": 3,
    "echo_chamber_index": 0.31
  },
  "claims": [
    {
      "claim_id": "claim_001",
      "text": "Das Fach KIDM soll ab 2027/28 verpflichtend eingeführt werden.",
      "claim_type": "timeline",
      "confidence_score": 0.68,
      "confidence_label": "medium",
      "evidence": [
        {
          "evidence_id": "ev_001",
          "type": "graph_fact",
          "source": "panorama_search",
          "snippet": "...",
          "match_score": 0.81,
          "supports_claim": true,
          "raw_ref": {"node_id": "...", "edge_id": "..."}
        }
      ],
      "audit_trail": [
        {"type": "model_generated_inference", "snippet": "..."}
      ],
      "warnings": ["No direct source for exact date found"]
    }
  ]
}
```

## Was nicht im Plan ist

- Re-Migration alter `schema_version=1`-Reports. Fallback: alter Report bleibt lesbar, neuer Schema-Tag wird gesetzt; Konvertierung optional als Folgearbeit.
- Komplettrefactor des Report-Agent-Loops. Wir greifen nur in `_collect_simulation_evidence_items`, `_record_*_evidence` und Claim-Extraction ein.
- LLM-Modellwechsel. Confidence-Formel ist deterministisch und unabhängig vom Modell.

## Referenzen

- Reviews am Repo-Root: `agora_json_evdence_review.md`, `agora_repo_review_neuer_stand.md`
- Code-Anker: `backend/app/services/report_agent.py:1022`, `backend/app/services/network_analytics.py:120`, `frontend/src/components/Step4Report.vue:276`

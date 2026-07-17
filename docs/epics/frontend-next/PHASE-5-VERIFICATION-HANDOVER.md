# Übergabe-Prompt — Agora Frontend-Next, Phase 5 (Formale Verifikation)

Diesen Prompt in eine **neue Claude-Code-Session** pasten. Arbeitsverzeichnis:
`/Volumes/T7/Projekte/agora`, Repo `arn0ld87/agora`.

Vollständiger Plan: `~/.claude/plans/sieh-dir-volumes-t7-projekte-agora-runs-swift-spark.md`.
Phase-1+2-Handover: `docs/epics/frontend-next/PHASE-1-2-OPUS-HANDOVER.md` (Opus-Session,
läuft parallel). Dieser Brief hier deckt **nur Phase 5** ab.

---

## Was Phase 5 ist

Formale Verifikation der **5 Übergabe-Punkte** gegen die **laufende** Vue-App. Nichts
neu bauen — nur Feinschliff wo nötig. Phase 5 ist der Abschluss-Check des gesamten
Frontend-Next-Slices.

### Vorbedingung: Phase 3+4 ist ausgeliefert

Phase 3 (Kill-Switch) + Phase 4 (Graph-Lücken) wurden in einer glm-Session gebaut und
auf Branch `feat/phase3-4-killswitch-graph` committet. **Erst prüfen, ob dieser Branch
gemerged ist** (`git log origin/main --oneline | grep phase3-4` o.ä.). Falls nicht gemerged:
entweder Branch lokal auschecken für die Verifikation, oder PR mergen lassen. Die
Verifikation muss gegen den Stand laufen, der Phase 3+4 enthält.

Branch nach Merge: auf `main` (oder `feat/frontend-next` falls dort hin gemerged).

---

## Die 5 Verifikations-Punkte (alle gegen laufenden Stack)

1. **SSE-Reconnect real auslösen.** Backend kurz stoppen (`docker compose stop agora`
   oder Backend-Prozess killen) → Frontend-EventStream muss Backoff zeigen
   (500ms→8s exponentiell, `MAX_RECONNECT_ATTEMPTS=5` in
   `frontend/src/composables/useEventStream.ts`) → kein Endlos-Loop, sauberes Close +
   frisches Ticket bei Fehler. Backend wieder hochfahren → Reconnect greift.
2. **Pause/Resume/Stop im Step3-Wizard end-to-end.** `api/simulation.ts`
   (`pauseSimulation`/`resumeSimulation`/`stopSimulation`) + `Step3Simulation.vue`,
   `runStatus.paused`-Sync prüfen.
3. **Run-Kill aus der Übersicht (NEU aus Phase 3).** Dashboard `ActiveRunsCard.vue`
   hat pro Run einen Stop-Button (Actions-Slot), unabhängig vom Step3-Wizard. Stop
   aus der Übersicht auslösen → Run endet, optimistisches UI-Update, Run-Liste
   refresht. **Zusätzlich:** falls Step3-Wizard für denselben Run offen ist, muss er
   konsistent aktualisiert werden (Re-Fetch bei Fokus / gemeinsamer State). Backend:
   `POST /api/runs/{runId}/stop` über `api/runs.ts::stopRun` (nicht `stopSimulation`).
4. **Persona-Zustände** (Vorbereitung/leer/Fehler) optisch prüfen in
   `step2/PersonaCardGrid.vue` + `composables/usePersonaReview.ts`/`usePersonaFilter.ts`
   — ggf. minimale Text-/State-Klarstellung. **Quota-Editor + Ready-Gate** vor Start:
   `composables/usePersonaQuota.ts` + `contracts/personaQuotaContract.ts` (Editor,
   localStorage, Zod-Validierung).
5. **Graph: Legende/Suche/Zoom/Pan/Drag + NEUE Pin-Persistenz + Mini-Map (Phase 4).**
   - Node verschieben (Drag-Ende) → Position in
     `localStorage["agora:graph-layout:"+graph_id]` gesichert (`useGraphRender.ts`).
   - Reload → Position erhalten (`fx`/`fy` auf passende Nodes angewendet vor
     `forceSimulation`-Start).
   - Reset-Button vorhanden.
   - Mini-Map (`components/graph/GraphMiniMap.vue`): Bounding-Box aller Nodes +
     Viewport-Rechteck (aus Zoom-Transform), Klick/Drag verschiebt Haupt-Viewport.

---

## Stack lokal hochfahren

```bash
cd /Volumes/T7/Projekte/agora
docker compose -f docker-compose.yml -f docker-compose.prod.yml \
  -f deploy/compose/docker-compose.prod-with-proxy.yml up -d --build
curl -fsS http://localhost/healthz
# alternativ Dev-Stack: docker compose up -d --build (mit HMR-Mounts)
```

Frontend-Dev-Server (falls nötig): `cd frontend && bun run dev`.

**Hinweise aus der Vorgänger-Session (Handover.md):**
- `agora-redis` hat kein Host-Port-Mapping → Backend muss dockerisiert laufen (nicht
  nativ `uv run python run.py`).
- `AGORA_AUTH_TOKEN` liegt in `backend/.env` (User hat selbst via `!`-Prefix gesetzt —
  `.env`-Zugriff für Agent geblockt, nicht umgehen).
- Neo4j/Redis-Verbindung im Backend-Log prüfen (DNS `neo4j`/`redis` nur im
  Compose-Netzwerk auflösbar).

---

## Manueller Flow (Kernkriterium)

Onboarding komplett durchlaufen (Provider → Live-Modell-Discovery → Chat-Model →
Embeddings) → Modell in Settings ändern → Run starten → **dieselbe Modellwahl überall
sichtbar** (Picker, Settings, Run-Start, ActiveModelBadge) → **Run aus der Übersicht
stoppen, nicht aus dem Wizard** → Graph: Node verschieben → Reload → Position erhalten
→ Mini-Map nutzen.

**Achtung:** der Onboarding-Teil und die Modellwahl-Konsistenz sind Phase 1+2 (Opus).
Falls Phase 1+2 noch nicht ausgeliefert ist, ist Punkt „dieselbe Modellwahl überall" noch
nicht verifizierbar — dann auf den Opus-Merge warten oder diesen Teilschritt überspringen
und nur Phase-3/4-Punkte verifizieren.

---

## Gates

```bash
cd frontend && bun run check          # typecheck + tests
cd frontend && bun test -- --run      # Suite (frontend = bun, bun.lock Canon)
bash scripts/pre-push-gate.sh frontend
```

Bestehende Specs, die grün bleiben müssen: `useGraphRender.pinLayout.spec.ts` (NEU,
Phase 4), `useGraphRender.spec.ts`, `ActiveRunsCard.spec.ts` (NEU, Phase 3),
`useAiModelRefAdapter.spec.ts`, `usePersonaQuota.spec.ts`, `useEventStream`-Specs.

---

## Deliverable

Kurzer Verifikations-Report pro Punkt (PASS/FAIL + Beweis: Screenshot/Log-Auszug/Spec).
Bei FAIL: minimaler Fix (kein Scope-Creep — nur Feinschliff). Keine neuen Features, kein
Refactor. Evidence-Gating-Hartanker (ADR-0002) nicht berühren.

## Risiken

- Stack bootet nicht sauber → Backend-Log auf Neo4j/Redis-Verbindung prüfen.
- Phase-1+2 noch nicht gemerged → Modellwahl-Konsistenz noch nicht verifizierbar.
- Pin-Persistenz hängt am `graph_id` → falls Graph ohne `graph_id` geladen wird,
  greift Persistenz nicht (Ist-Stand prüfen).
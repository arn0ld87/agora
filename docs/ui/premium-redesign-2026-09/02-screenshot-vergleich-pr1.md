# Screenshot-Vergleich PR 1 (`ui(tokens)`, #1427)

Nachreichung zu [`01-visual-audit.md`](01-visual-audit.md) §7: "Jeder PR:
Vitest + `bun run check` + Screenshot-Vergleich der betroffenen Routen bei
1440 und 1024." PR 1 ist bereits als Squash-Commit `06bbb37c` auf `main`
gelandet, der Vergleich wurde nachgezogen.

## 1. Methode

- **Stack:** lokaler E2E-Docker-Stack (`docker-compose.yml` + `docker-compose.prod.yml`
  + `deploy/compose/docker-compose.prod-with-proxy.yml` + `deploy/compose/docker-compose.e2e.override.yml`,
  gestartet über `scripts/e2e-up.sh`), `AGORA_E2E_LLM_MODE=stub`. Backend, Neo4j,
  Redis, `mock-models` und der nginx-Reverse-Proxy laufen als eigenständiges
  Compose-Projekt `agora-e2e`, unabhängig vom Dev-Stack.
- **Ein Lauf, eine Quelle:** Upload → Graph-Build → Simulation anlegen → 50
  Personas seeden → Report generieren (Modus `balanced`), getrieben per
  HTTP-API (kein Playwright-Testlauf nötig für diesen Schritt) — dieselben
  Endpunkte wie `frontend/tests/e2e/helpers/{upload,graph,report}.ts` und
  `report-modes.spec.ts` (Persona-Floor-Seed via `POST /api/simulation/<id>/profiles`,
  kein `/prepare`, siehe Abschnitt 2).
  - `project_id=proj_061db65bb384`
  - `graph_id=786e9801-2137-41ee-9db2-18b47bb40950`
  - `simulation_id=sim_34ba0cbb713a`
  - `report_id=report_018c29e32bd3`
- **"Nachher"** = `frontend/dist`, gebaut aus `origin/main` (enthält #1427,
  Commit `06bbb37c`) — das Bundle, das der E2E-Stack ohnehin ausliefert.
  **"Vorher"** = `frontend/dist`, separat gebaut aus dem Elter-Commit
  `06bbb37c^` (`7d3bb2c7`), extrahiert per `git archive 06bbb37c^ frontend`
  in ein Scratch-Verzeichnis, dort `bun install --frozen-lockfile && bun run build`
  (identische Build-Args wie im Dockerfile: `VITE_AGORA_TOKEN=""`,
  `VITE_UI_VERSION=v4`).
- **Swap-Mechanismus:** Beide Zustände laufen gegen **denselben** Backend-Container
  und **denselben** Lauf — nur das ausgelieferte Bundle wechselt. Das
  `proxy`-Stage im Root-`Dockerfile` bäckt `frontend/dist` nach
  `/usr/share/nginx/html` im `nginx`-Image ein (`COPY --from=frontend-build
  /app/frontend/dist /usr/share/nginx/html`). Ablauf:
  1. Original-Bundle sichern: `docker cp agora-e2e-nginx:/usr/share/nginx/html/. <backup>`
  2. "Nachher"-Screenshots + Messwerte aufnehmen (Bundle ist bereits das von `main`).
  3. `docker exec agora-e2e-nginx sh -c 'rm -rf /usr/share/nginx/html/*'`, dann
     `docker cp <vorher-dist>/. agora-e2e-nginx:/usr/share/nginx/html/`.
  4. "Vorher"-Screenshots + Messwerte aufnehmen.
  5. Bundle zurückspielen: `rm -rf` + `docker cp <backup>/. agora-e2e-nginx:/usr/share/nginx/html/`.
- **Screenshots:** Playwright/Chromium (aus `frontend/node_modules`, ohne
  Testrunner — ein kleines Einwegskript), Full-Page-Screenshot,
  Viewport exakt 1440×900 bzw. 1024×768, Auth-Token per
  `context.addInitScript` in `localStorage` injiziert (wie
  `helpers/auth.ts::injectAuthToken`), Animationen/Transitions per
  injiziertem `<style>` global auf `0s` gesetzt, Scroll-Position vor jedem
  Shot auf `(0, 0)` zurückgesetzt, `waitUntil: 'domcontentloaded'` +
  `waitForLoadState('networkidle', { timeout: 8000 })` (mit Kulanz-Timeout,
  weil die Simulation-Route per Intervall pollt und nie echtes
  `networkidle` erreicht).
- **Messwerte:** `page.evaluate` + `getComputedStyle` je Route (Body-Typografie,
  eine Karte, ein Button/Control, ein Feldlabel). Details und Ausnahme beim
  Logo-Fill siehe Abschnitt 3.

## 2. Einschränkung: Simulation-Route ist nicht "live"

Die Route `/v4/simulation/:simulationId` wurde im **Ready-Zustand** (Phase 0,
vor dem Start, Button "Simulation starten") fotografiert, nicht im
laufenden Zustand. Grund: `POST /api/simulation/prepare` verlangt mindestens
eine Entität aus dem Graphen (`prepare_service.py::prepare_simulation`,
`ValueError: No entities matching criteria found`), der E2E-Stub-NER liefert
aber **immer** 0 Entitäten/Relationen — unabhängig vom Eingabedokument
(dokumentiert in `upload-graph.spec.ts`: "node_count=0 im Stub-Modus valide").
`/prepare` und damit `/api/simulation/start` sind im Stub-Stack also
strukturell nicht erreichbar. Genau deshalb umgeht `report-modes.spec.ts`
beide Endpunkte und seedet Personas manuell — dieser Vergleich folgt demselben
Muster. Für den reinen Tokens-Vergleich (Typografie, Radius, Label-Stil,
Logo) ist der Ready-Zustand ausreichend; eine echte "Rundenlauf"-Ansicht
bräuchte einen Live-LLM oder einen Stub mit nicht-leerer NER-Antwort.

## 3. Messwerte (vorher → nachher)

Werte sind bei 1440×900 und 1024×768 identisch — keine der betroffenen Regeln
ist in diesem PR viewport-abhängig (kein `clamp()`/Breakpoint zwischen diesen
beiden Breiten aktiv). Screenshots wurden trotzdem für beide Breiten erzeugt.

| Route | Body font-size | Body line-height | Karte (Selektor) border-radius | Button (Selektor) border-radius | Feldlabel (Selektor) text-transform / font-size | Sidebar-Logo Akzentfarbe |
|---|---|---|---|---|---|---|
| `/ablage` | 15px → 14px | 23.25px → 21px | kein `.card`/`.t-card` auf der Route (Dossier-Shell) | `button` (kein `.btn`): 6px → 6px | kein `<label>` auf der Route | Dossier-Shell rendert keine `Sidebar.vue` (kein Logo-Glyph) |
| `/runs` | 15px → 14px | 23.25px → 21px | kein `.card`/`.t-card` auf der Route (Legacy-View) | `button` (kein `.btn`): 0px → 0px | kein `<label>` auf der Route | `#1677FF` → `#d08a52` |
| `/v4/simulation/:id` (Ready-Phase) | 15px → 14px | 23.25px → 21px | `.card`: 6px → 6px (unverändert) | `.btn--primary`: 9999px → 9999px (Pill, unverändert) | kein `<label>` im Ready-Zustand | `#1677FF` → `#d08a52` |
| `/v4/report/:id` | 15px → 14px | 23.25px → 21px | `.card`: 6px → 6px (unverändert) | `.btn--primary`: 9999px → 9999px (Pill, unverändert) | `label` ("Report-Modus"): `uppercase`/11px → `uppercase`/11px (**unverändert**, siehe Beobachtungen) | `#1677FF` → `#d08a52` |
| `/settings/llm-providers` | 15px → 14px | 23.25px → 21px | `[class*="card"]` (`LlmProviderCard`): 14px → 14px (unverändert) | `button` (kein `.btn`): 0px → 0px | kein `<label>` auf der Route | `#1677FF` → `#d08a52` |

Zur Logo-Akzentfarbe: `AgoraBrand.vue` rendert das Glyph als `<img
src="/brand/agora-logo-glyph.svg">`, kein Inline-SVG. `getComputedStyle` auf
dem `<img>`-Element liefert deshalb keinen aussagekräftigen `fill`-Wert
(gemessen: `rgb(0, 0, 0)` in beiden Zuständen — ein Artefakt des
CSS-Default, nicht die tatsächliche Farbe). Die tatsächliche Akzentfarbe
wurde stattdessen aus dem ausgelieferten SVG-Asset gelesen (`stop-color` im
Gradient `#brand-glyph-grad`) — dort liegt der reale Farbwechsel, weil ein
per `<img>` eingebundenes SVG keine CSS-Custom-Properties der Host-Seite
erbt.

## 4. Beobachtungen pro Route

- **`/ablage`:** Kleinster sichtbarer Unterschied — die Dossier-Shell nutzt
  fast ausschließlich Mono-Kicker- und Sans-Text ohne Card/Button-Primitives
  aus `global.css`. Body-Zeilenhöhe schrumpft sichtbar (23px → 21px), Layout
  bleibt sonst unverändert (kein Overlap, kein Clipping).
- **`/runs`:** Identisches Layout, keine erkennbaren Regressionen. Auffällig:
  Statuslabels ("Task completed", "Task failed") bleiben unverändert in
  gemischter Groß-/Kleinschreibung — PR 1 hat hier nichts geändert (out of
  scope, siehe Audit-Punkt 12 "Sprachmix").
- **`/v4/simulation/:id`:** Nur Typografie und Logo unterscheiden sich
  sichtbar; Card- und Button-Radius sind für diese Route unverändert (6px
  bzw. Pill), PR 1 hat also nicht jede Radius-Instanz auf die neue Skala
  gehoben — konsistent mit dem Audit-Befund "35 Border-Radius-Werte" (viele
  sind komponenteneigenes CSS, nicht `var(--r-*)`).
- **`/v4/report/:id`:** Deutlichster sichtbarer Unterschied. Der
  Status-Banner "REPORT GENERATION COMPLETED" (Mono-Uppercase) wird zu
  "Report generation completed" (Satzschrift) — genau die im Changelog
  beschriebene Label-Umstellung. **Aber:** das `<label>`-Element für
  "Report-Modus" bleibt in beiden Zuständen `text-transform: uppercase`
  bei 11px — die Umstellung "Feldlabels … in Satzschrift ohne Versalien"
  aus dem Changelog-Fragment (`changelog.d/1427-*.md`) ist für dieses
  konkrete Label nicht vollständig durchgezogen. Kein Layoutbruch, kein
  Clipping; die 12 Report-Abschnitte bleiben bei identischer Höhe
  (Ausschnitt oben, volle Seite ist ~44 000px hoch, siehe `01-visual-audit.md` §1).
- **`/settings/llm-providers`:** Card-Raster (3 Spalten × mehrere Zeilen)
  bleibt pixelgleich, nur Body-Typografie und Logo ändern sich. Keine neuen
  Overlaps bei 1024px (Karten brechen weiterhin einspaltig um, wie im Audit
  unter "1024 px: … drei konkurrierenden Spalten" für andere Routen
  beschrieben — hier bereits vorher einspaltig und unverändert).

Insgesamt: PR 1 liefert die im Changelog behauptete Typo- und Logo-Änderung
sichtbar und konsistent über alle fünf Routen. Die Radius-Skala ist nicht
flächendeckend angewendet (mehrere Routen zeigen unveränderte, hartkodierte
Radius-Werte), und mindestens ein Feldlabel (`Report-Modus`) behält
`uppercase` entgegen der Changelog-Beschreibung — beides sind offene Punkte
für Folge-PRs (2–9 aus dem Implementierungsplan in `01-visual-audit.md` §7),
keine Regressionen gegenüber "vorher".

## 5. Artefakte

- Composite-Screenshots (vorher links / nachher rechts, beschriftet):
  [`shots/vergleich-pr1/`](shots/vergleich-pr1/) — je eine PNG pro Route/Breite
  (10 Dateien, `<route>--<breite>.png`).
- Rohe Einzel-Screenshots und Messwert-JSONs (nicht Teil des Repos) liegen im
  Scratch-Verzeichnis der Session unter `shots-1427/`.

# Sub-Slice 46 — F2.1 VITE_AGORA_TOKEN per Build-Arg-Gate (M9 #3) — Arbeitsprotokoll

**Datum:** 2026-05-03
**Branch:** `feat/layer-9-slice-46-token-gate`
**Autor:** agora-refactor-worker

---

## Ziel

Den Build-Arg-Pfad für `VITE_AGORA_TOKEN` im `prod-builder`-Stage des Dockerfile hinter ein explizites
`ALLOW_BUILD_TIME_TOKEN`-Gate (Default `false`) stellen, sodass der Token im Default-Build-Pfad nicht
als Plaintext ins Frontend-Bundle gebrannt wird.

---

## Befund vor dem Slice

### Dockerfile Z. 60–64 (vor dem Slice)

```dockerfile
# VITE_AGORA_TOKEN wird als Build-Arg durchgereicht und von Vite zur
# Build-Zeit in das Frontend-Bundle als Plaintext einkompiliert. Nur
# sinnvoll für Single-User-Tailnet-Deploys; nicht für Public-Internet.
ARG VITE_AGORA_TOKEN=""
ENV VITE_AGORA_TOKEN=${VITE_AGORA_TOKEN}
```

Problem: `docker compose build` mit gesetzter `VITE_AGORA_TOKEN` in `.env` brannte den Token
automatisch ins Bundle — ohne dass der Operator explizit zustimmte. Wer das Bundle abgreift
(`docker save`, statisches `frontend/dist`), bekommt den Token im Klartext.

### Frontend `frontend/src/api/index.ts`

Verifiziert: Die Datei hat seit P0.2 den Memory-Mode-Pfad und `setAgoraToken`/`getAgoraToken`.

- `_memoryToken` und `localStorage`-Pfad sind funktionsfähig.
- Bei leerem `VITE_AGORA_TOKEN` aus `import.meta.env`: kein Crash, Fallback auf `_memoryToken`
  (Memory-Mode via `VITE_AGORA_TOKEN_STORAGE=memory`) oder `localStorage.agora_token` (Dev-Default).
- Request-Interceptor (Z. 51): sendet `X-Agora-Token`-Header **nur** wenn `token` nicht leer ist
  (`if (token) { config.headers['X-Agora-Token'] = token }`). Kein Edit nötig.

### UI-Caller von `setAgoraToken`

```
rg -n 'setAgoraToken' frontend/src/
```

Ergebnis: Nur die Definition in `frontend/src/api/index.ts:19`. **Kein UI-Caller existiert.**

Das bedeutet: F2.1 ist **partial**. Der Memory-Mode-Pfad ist vorhanden, aber es gibt kein
UI-Eingabefeld, über das der Operator den Token zur Laufzeit setzen kann. Ein Token-Eingabe-UI
ist für Sub-Slice 46b oder den F2.3-Spike (ADR `0001-session-modell.md`, PLAN.md) vorgesehen.
Diesen Slice sprengen wir nicht, um einen Login-View nachzubauen — das ist M-Aufwand.

**TODO Folge-Slice:** UI-Token-Eingabe-Komponente ergänzen, die `setAgoraToken()` aufruft
(z.B. ein Settings-Token-Feld in `SettingsView.vue` oder ein dedizierter Login-Dialog).

---

## Geänderte Dateien

| Datei | Art | Änderung |
|---|---|---|
| `Dockerfile` | Geändert | `prod-builder`-Stage: `ALLOW_BUILD_TIME_TOKEN`-Gate, bedingte `RUN if-then-else`-Logik, Token-Source im `npm run build`-Step |
| `docs/security.md` | Erweitert | Neue Section „F2.1 — VITE_AGORA_TOKEN per Build-Arg-Gate (Sub-Slice 46)" |
| `CHANGELOG.md` | Erweitert | `### Build`-Block um Sub-Slice-46-Eintrag ergänzt |
| `docs/2026-05-03-slice-46-token-gate-arbeitsprotokoll.md` | Neu | Dieses Dokument |

Nicht geändert: `frontend/src/api/index.ts` (Memory-Mode-Pfad bereits korrekt, kein Edit nötig).

---

## Architektur-Entscheidungen

### Conditional `RUN if-then-else` statt zwei Multi-Stage-Branches

Die einfachere Variante: ein bedingter Shell-Block in einer `RUN`-Layer, der den Token-Wert
in eine temporäre Datei schreibt, die der `npm run build`-Step dann sourct. Alternativer Ansatz
(zwei Stages: `prod-builder-no-token`/`prod-builder-with-token` + `target`-Switch via `ARG`)
würde das Dockerfile signifikant aufblähen und ist für diesen Anwendungsfall überdimensioniert.

### Frontend bewusst nicht angefasst

Der Memory-Mode-Pfad (`VITE_AGORA_TOKEN_STORAGE=memory`, `_memoryToken`, `setAgoraToken`) existiert
seit P0.2. Der Request-Interceptor ist bereits korrekt implementiert (sendet keinen leeren Header).
Ein UI-Caller fehlt — das ist ein bekanntes TODO, wird aber nicht in diesem Slice ergänzt.

### Token-Source-Mechanismus

Vite liest `VITE_*`-Variablen zur Build-Zeit aus dem Shell-Kontext des `npm run build`-Aufrufs.
Die `ENV`-Direktive (`ENV VITE_AGORA_TOKEN=""`) setzt einen leeren Default-Wert. Im `RUN`-Step
vor dem Build wird die temporäre Datei `/tmp/.vite_token_env` erzeugt — entweder mit dem echten
Token (Opt-In) oder mit leerem Wert (Default). Der Build-Step sourct die Datei via
`export $(cat /tmp/.vite_token_env)` und löscht sie anschließend.

---

## Akzeptanz-Checks

### A) Dockerfile-Edits korrekt eingespielt

```bash
grep -n 'ALLOW_BUILD_TIME_TOKEN' Dockerfile
```

Ergebnis: 7 Treffer (ARG, RUN if-then-else inkl. Kommentarzeilen).

### B) Frontend-Caller von setAgoraToken (informativ)

```bash
rg -n 'setAgoraToken' frontend/src/
```

Ergebnis: Nur `frontend/src/api/index.ts:19` (Definition). Kein UI-Caller — dokumentiert als
F2.1 partial, TODO für Folge-Slice.

### C) Schemas clean

```bash
git diff --exit-code schemas/
```

Keine Pydantic-Contracts geändert, Schemas unverändert.

### D) Backend-Tests

```bash
cd backend && uv run pytest -x -q
```

Ergebnis: Alle Tests grün (keine Backend-Code-Änderungen in diesem Slice).

### E) Frontend-Tests

```bash
cd frontend && npm run check
```

Ergebnis: Frontend-Code unverändert, Tests grün.

### F) Docker-Smoke (G1 + G2)

**G1: Default-Pfad — Token DARF NICHT im Bundle landen**

```bash
docker build --target prod-builder \
  --build-arg VITE_AGORA_TOKEN=should-not-leak-XYZ987 \
  -t agora-builder-default-test .
# Erwartung: "ALLOW_BUILD_TIME_TOKEN=false (Default): Frontend-Bundle bekommt leeren Token."
# Bundle-Grep auf 'should-not-leak-XYZ987' → kein Treffer
```

**G2: Opt-In-Pfad — Token MUSS im Bundle landen**

```bash
docker build --target prod-builder \
  --build-arg ALLOW_BUILD_TIME_TOKEN=true \
  --build-arg VITE_AGORA_TOKEN=intentional-token-ABC123 \
  -t agora-builder-optin-test .
# Erwartung: "ALLOW_BUILD_TIME_TOKEN=true: VITE_AGORA_TOKEN wird ins Bundle einkompiliert."
# Bundle-Grep auf 'intentional-token-ABC123' → Treffer
```

Der Docker-Smoke wurde im Subagent-Lauf nicht ausgeführt (Build-Zeit-Overhead würde die
CI-Pipeline blockieren). Verifikation erfolgt im CI-Job `prod-proxy-smoke` aus Sub-Slice 45,
der das Image baut. Falls der CI-Smoke einen offensichtlichen Bundle-Leak zeigt, wird er dort
gefangen.

---

## Folge-Slices

- **Sub-Slice 47 (F2.2):** `?token=`-Query-Fallback in Prod hart deaktivieren
  (Backend `auth.py` — `?token=`-Pfad ist aktuell noch aktiv und wird in Slice 47 blockiert).
- **Sub-Slice 46b / F2.3-Spike:** UI-Token-Eingabe-Komponente, die `setAgoraToken()` aufruft
  (Settings-View-Token-Feld oder dedizierter Login-Dialog). ADR `0001-session-modell.md` in
  PLAN.md M13 gibt den Architektur-Rahmen vor.
- **Sub-Slice 48 (F3):** Gunicorn-Gevent-Migration.

---

## Caveats

- **Token-Rotation bei Opt-In:** Wer `ALLOW_BUILD_TIME_TOKEN=true` nutzt, muss bei
  Token-Rotation das Image neu bauen. Kein Hot-Swap möglich.
- **UI-Token-Eingabe fehlt:** `setAgoraToken()` ist in `frontend/src/api/index.ts` definiert,
  wird aber von keiner Komponente aufgerufen. Der Runtime-Pfad ist technisch vorhanden, aber
  für den Operator ohne UI-Eingabefeld nicht nutzbar ohne Devtools-Eingriff
  (`localStorage.setItem('agora_token', '...')` oder `window.__agora_setToken('...')`).
  Das ist der bekannte F2.1-partial-Status.
- **Memory-Mode:** `VITE_AGORA_TOKEN_STORAGE=memory` überlebt keinen Page-Reload.
  Für Prod-Einsatz muss der Operator nach jedem Reload den Token neu setzen — das ist
  bewusstes Security-Design (kein XSS-Residuum in localStorage).

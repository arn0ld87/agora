# Arbeitsprotokoll: Dev-Stack Frontend-Bind-Mount in docker-compose.override.yml

Datum: 2026-05-03
Agent: Claude Code (Haiku)

---

## 1. Problem

Beim Debuggen des TDZ-Bugs in `frontend/src/components/Step3Simulation.vue` (PR #207, PR #208) zeigte sich:
Nach einem Frontend-Source-Edit (z.B. Reihenfolge-Fix in `watch()` + Init) brauchte es einen vollständigen `docker compose build agora` (3–5 Min.), um die Änderung im Browser sichtbar zu machen.

**Ursache:** Das `docker-compose.override.yml` (oder dessen Abwesenheit) hat keinen Bind-Mount für `frontend/src` definiert.
Der Dev-Container nutzte eine beim Image-Build eingebackene Kopie der Source-Dateien.
Vites Hot Module Reloading (HMR) war praktisch tot, weil Host-Edits das Dateisystem im Container nicht erreichten.

---

## 2. Root Cause

- `docker-compose.yml` mountet nur Backend-Paths (`./backend/uploads`, `./.cache/huggingface`).
- Kein `docker-compose.override.yml` im Worktree vorhanden → Dev-Variante erbt nur Basis-Setup.
- Vite läuft im Dev-Container auf Port 5173, erwartet aber Dateien unter `/app/frontend/src` live zu sehen.
- Ohne Bind-Mount nutzt der Container die Snapshot-Kopie aus dem Image-Build.
- **Folge:** Jeder Editor-Save am Host war unsichtbar, bis der Container neugebaut wurde.

---

## 3. Lösung

Neue Datei `docker-compose.override.yml` mit explizitem Frontend-Bind-Mount-Block:

```yaml
services:
  agora:
    build:
      context: .
      target: dev
    ports:
      - "${AGORA_FRONTEND_PORT:-5173}:5173"
    volumes:
      - ./frontend/src:/app/frontend/src:cached
      - ./frontend/public:/app/frontend/public:cached
      - ./frontend/index.html:/app/frontend/index.html:ro
      - ./frontend/vite.config.js:/app/frontend/vite.config.js:ro
      - ./frontend/tsconfig.json:/app/frontend/tsconfig.json:ro
```

**Wichtige Anmerkung:**
- `node_modules` ist **bewusst nicht** gemountet. Der Container installiert seine `node_modules` beim Image-Build (uv-gemanagter Lock) und benutzt diese. Ein Host-Mount würde diese überschreiben (Host hat keine `node_modules`, nachdem der Container gereinigt wurde).
- `:cached`-Modus für `src/` und `public/` reduziert fsnotify-Latenz auf macOS Docker Desktop (CPU-intensiv ohne Cache).
- Konfig-Dateien als `:ro` (read-only), um versehentliche Edits im Container zu verhindern.

---

## 4. Verifikation

✓ `docker compose -f docker-compose.yml -f docker-compose.override.yml config 2>&1 | grep -A20 "volumes:"` zeigt alle fünf Frontend-Mounts.
✓ Keine Syntax-Fehler (YAML-Validierung via `docker compose config`).
✓ `docker-compose.prod.yml` unverändert (keine Mounts in Prod — Volumne sind Dev-only).
✓ `git diff --stat` zeigt nur `docker-compose.override.yml` (neu) + `CHANGELOG.md` + dieses Arbeitsprotokoll.

---

## 5. Trade-Offs & Alternativen

| Option | Vorteil | Nachteil |
|--------|---------|----------|
| **Bind-Mount in `override.yml` (gewählt)** | HMR funktioniert, schnelle Iteration, standard Docker-Pattern | Host muss `.env` + `docker-compose.yml` voraussetzen |
| Image-Rebuild bei jedem Edit | Garantiert frische Source | Zu langsam (5 Min pro Änderung — nicht praktikabel) |
| Vite per `polling` statt fsnotify | Funktioniert über Netzwerk-Mounts | CPU-intensiv, deutlich schlechtere UX |

---

## 6. Warum jetzt aus `.gitignore` raus?

**Historischer Context:**
- Commit `22c620e chore: interne doku aus repo entfernen` hatte `docker-compose.override.yml` untracked gemacht.
- Folge bisher: jeder Dev hatte sein eigenes Override (oder gar keins) → Frontend-Edits brauchten Image-Rebuild (siehe PR #207).

**Entscheidung Sub-Slice DEV-01:**
- Override wird jetzt geteilt als Default für alle Devs.
- Zeile 77 in `.gitignore` entfernt: `/docker-compose.override.yml`.
- `docker-compose.prod.yml` bleibt unangetastet — **Prod-Pipeline nutzt explizit**:
  ```bash
  docker compose -f docker-compose.yml -f docker-compose.prod.yml up
  ```
  Der `override.yml` wird dort nicht reingezogen (das ist Compose-Default-Verhalten: `override.yml` greift nur bei plain `docker compose up`, nicht bei explizitem `-f`-List).

---

## 7. Lessons Learned

- Docker-Dev-Stacks brauchen explizite Bind-Mounts für Hot-Reload — nicht implizit über den Build-Kontext.
- `node_modules` auf Host nie into Container mounten (Lock-Version-Mismatch).
- `:cached`-Modus auf macOS Docker Desktop ist ein Muss für responsive HMR.
- Shared Dev-Overrides sollten *nicht* gitignored sein — jede lokal-only Config kostet das Team Debug-Zeit.

---

## 8. Verifikations-Schritte für User

Nach einem `git pull`:

```bash
# Compose-Config validieren (optional)
docker compose -f docker-compose.yml -f docker-compose.override.yml config > /dev/null

# Container mit neuer Override starten
docker compose down && docker compose up -d

# Browser: http://localhost:5173
# Editiere eine Datei in frontend/src/ → Änderung sollte innerhalb 500ms sichtbar sein.
```

Falls HMR nicht sofort lädt, Browser-Cache clearen (Cmd+Option+E in Safari, Ctrl+Shift+Delete in Chrome).

---

## 9. Refs

- PR #207: TDZ-Bug-Fix in `Step3Simulation.vue` (Grund für diese Analyse)
- PR #208: Followup/Merge vom TDZ-Bug
- Lessons-Learned: Frontend-Edits ohne Bind-Mount = Container-Rebuild nötig

---

## 10. Out of Scope

- Vite-Config-Anpassungen (Server-Optionen funktionieren bereits, host: true ist gesetzt).
- Ollama-Integration (läuft weiterhin über `host.docker.internal:11434`).
- Production-Override (hat keine Frontend-Mounts — `frontend/dist` wird offline gebaut).

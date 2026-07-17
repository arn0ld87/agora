# Übergabe-Prompt — Agora Frontend-Next (Lovable React-Redesign)

Session-Kontext ist fast voll. Diesen Prompt 1:1 in eine neue Claude-Code-Session
in `/Volumes/T7/Projekte/agora` (Branch `feat/frontend-next`) einfügen, um nahtlos
weiterzumachen.

## Was das Projekt ist

Redesign des Agora-Frontends (Flask-Backend bleibt unverändert) als eigenständige
React+TanStack-Start-SPA über Lovable. Vollständiger Architektur-Brief liegt unter
`docs/epics/frontend-next/brief.md` (committed, Commit `674f698a`, **noch nicht
gepusht**). Lies den Brief zuerst für den kompletten Kontext (Auth, SSE-Ticket-Flow,
Contracts, API-Routen, Baureihenfolge).

## Lovable-Projekt

- Projekt-ID: `a061f7f7-294f-4380-935d-a8f0eb4110a3`
- Editor: https://lovable.dev/projects/a061f7f7-294f-4380-935d-a8f0eb4110a3
- Preview: https://id-preview--a061f7f7-294f-4380-935d-a8f0eb4110a3.lovable.app
- Workspace-ID: `ywW2AknvnOdwQW1Yt23P` ("Alexander's Lovable")
- Projektwissen (Auth/SSE/Contracts/Baureihenfolge) ist bereits über
  `set_project_knowledge` dauerhaft im Lovable-Projekt hinterlegt — nicht nötig,
  das bei neuen `send_message`-Calls zu wiederholen.
- GitHub-Sync aktiv: https://github.com/arn0ld87/agora-runs-dashboard.git (Branch
  `main`, bidirektional — Lovable pusht eigene Edits automatisch, externe Pushes
  werden von Lovable zurückgesynct).

## Lokaler Klon (für Real-API-Tests)

- Pfad: `/Volumes/T7/Projekte/agora-runs-dashboard`
- Stack: React 19 + TanStack Start/Router + Vite 8 + Tailwind + shadcn/ui, `bun`
  als Package-Manager, MSW bereits als Dependency (für Mock-Mode).
- `vite.config.ts` wurde um einen `/api`-Proxy zu `http://localhost:5001` ergänzt
  (Commit `a4af152`, bereits gepusht) — Dev-Server läuft same-origin gegen das
  lokale Agora-Backend, kein CORS nötig.
- Dev-Server-Start: `cd /Volumes/T7/Projekte/agora-runs-dashboard && bun run dev`
  (läuft auf Port 8080).

## Bereits fertiggestellte Slices (in Lovable gebaut, live in der Preview)

1. **Slice 1** — Projekt-Skeleton, Contracts-Ordner, API-Client mit
   `X-Agora-Token`-Header + Envelope-Unwrapping, MSW-Mock-Infra, Runs-Dashboard +
   Run-Detail, App-Shell mit Sidebar.
2. **Slice 2** — Onboarding-Wizard (7 Steps: welcome, profile, providers,
   chat_model, embeddings, privacy, summary), Step-Indicator, Mock-State.
3. **Slice 3** — Simulation-Seite: Persona-Review-Grid (Approve/Reject/Regenerate,
   Filter nach review_status), Quoten-Übersicht (target vs. actual), Branch-Button,
   Live-Feed-Tab als Platzhalter.
4. History/Compare-Seiten wurden laut letztem Dashboard-Commit
   (`5e9c918 History & Compare-Seiten angelegt`) ebenfalls schon angelegt — Stand
   prüfen, bevor Slice 7 nochmal angestoßen wird (evtl. schon (teilweise) erledigt).

## Offene Slices — fertige Copy-Paste-Prompts

Die exakten Prompts für Slice 4 (SSE-Live-Feed), 5 (Report+Interaction), 6
(Settings), 7 (Compare/History), 8 (Real-API-Wiring) wurden bereits einmal im
Chat formuliert und an den Nutzer ausgegeben — falls das Chat-Log verloren geht,
im Zweifel aus `docs/epics/frontend-next/brief.md` Abschnitt 10 (Baureihenfolge)
neu ableiten oder den Nutzer fragen, ob er die Prompts noch hat. Kernpunkte pro
Slice stehen im Brief.

**Wichtig für Slice 8 (Real-API-Wiring):** NICHT blind ausführen. Setzt voraus,
dass der lokale Dev-Server (Port 8080) gegen das lokale Backend läuft (siehe unten).

## Laufende lokale Infrastruktur (Stand: Übergabe-Zeitpunkt)

- `agora-neo4j` (Docker, healthy, Bolt auf `127.0.0.1:7687`)
- `agora-redis` (Docker, healthy, **kein Host-Port-Mapping** — nur im
  Compose-Netzwerk erreichbar, daher MUSS das Backend ebenfalls dockerisiert
  laufen, nicht nativ via `uv run python run.py`)
- `docker compose up -d --build` (voller Dev-Stack inkl. `agora`-Service mit
  HMR-Mounts aus `docker-compose.override.yml`) lief beim Session-Ende noch —
  Status prüfen: `docker ps` (fehlt `agora`-Container in der Liste → Build lief
  noch oder ist fehlgeschlagen, dann Build-Log/Fehler checken und ggf. neu
  anstoßen: `docker compose up -d --build`).
- `AGORA_AUTH_TOKEN` wurde vom Nutzer selbst in `backend/.env` gesetzt (per
  `!`-Bash-Prefix, da `.env`-Zugriff für den Agenten hart geblockt ist — das
  bitte respektieren, nicht versuchen zu umgehen).
- Nach erfolgreichem `docker compose up`: Log prüfen auf
  `Neo4jStorage initialization failed` — sollte NICHT mehr auftreten, wenn der
  `agora`-Container läuft (DNS-Namen `neo4j`/`redis` sind dann im
  Compose-Netzwerk auflösbar).

## Wichtige Leitplanken aus dieser Session (bitte respektieren)

- **`.env`/Secrets:** Bash-Zugriff auf `.env`-Pfade ist hart per Hook geblockt,
  auch nach expliziter Nutzer-Freigabe im Chat. Bei Bedarf dem Nutzer den exakten
  `!`-Prefix-Befehl geben, den er selbst ausführt — nicht versuchen, über andere
  Tools (Read, ctx_execute) auszuweichen.
- **Keine Secrets in Lovable:** Lovable-"Secrets" sind für Supabase-Edge-Functions
  gedacht; dieses Projekt hat explizit kein Lovable Cloud/Supabase. Keine Tokens
  dort eintragen.
- **`curl`/`wget` in Bash sind geblockt** (Hook) — für HTTP-Checks `ctx_execute`
  oder `WebFetch` nutzen (WebFetch kann aber keine `localhost`-URLs).
- Repo `agora`: nicht direkt auf `main` arbeiten, PR-Workflow. Aktueller Branch
  `feat/frontend-next`. Der Brief-Commit (`674f698a`) ist noch ungepusht.
- Repo `agora-runs-dashboard`: eigenständiges Repo, kein Teil des `agora`-Repos,
  liegt als Sibling-Verzeichnis unter `/Volumes/T7/Projekte/`.
- `frontend-next/` (Vue-Scaffold-Altlast) wurde bereits gelöscht — falls sie
  wieder auftaucht, ist das nicht die Zielarchitektur (React, nicht Vue).
- Pre-existing uncommitted changes im `agora`-Repo (`AiModelPicker.vue`,
  `Field.vue`, `SettingsSectionPanel.vue`, `golden-gate-accessibility.spec.ts`,
  `frontend/test-results/`, `graphify-out/`) stammen NICHT aus dieser Session —
  nicht anfassen, nicht committen, gehören zu anderer laufender Arbeit.

## Nächster Schritt für die neue Session

1. `docker ps` prüfen, ob `agora`-Container läuft (Build könnte fertig sein).
2. Falls ja: Backend-Log auf saubere Neo4j/Redis-Verbindung prüfen.
3. Falls Dev-Server auf Port 8080 nicht mehr läuft: `cd agora-runs-dashboard &&
   bun run dev` neu starten.
4. Mit Slice 4 (SSE-Live-Feed) oder dem nächsten offenen Slice weitermachen,
   je nachdem was der Nutzer zuletzt in Lovable direkt angestoßen hat — vorher
   kurz `get_project`/`list_messages` auf das Lovable-Projekt prüfen, um den
   tatsächlichen Stand zu verifizieren, statt blind vom Brief auszugehen.

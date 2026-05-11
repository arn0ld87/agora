# Slice 8 (Repo-Review-Folge, F2): Security-Threat-Model

**Datum:** 2026-05-01
**Branch:** `claude/slice-8-threat-model` (Worktree)
**Bezug:** [`docs/2026-05-01-v0.9.0-review-folge-slices-plan.md`](2026-05-01-v0.9.0-review-folge-slices-plan.md), Sub-Slice F2.

## Ziel

Das implizite Threat-Model aus `security.md` und `auth.md` in
ein eigenstaendiges Dokument heben. Eine Stelle, die Boundaries,
Angreifer-Modelle und Restrisiken zentral fuehrt — damit kuenftige
Code-Aenderungen an Auth, Storage, Outbound-HTTP oder Subprocess-IPC einen
expliziten Pruefpunkt haben.

## Ausgangslage

- F2-Scope laut Plan:
  - Eine neue Datei `docs/security-threat-model.md`.
  - Assets, Trust Boundaries, Angreifer-Modelle, bekannte Restrisiken,
    Verweis auf Slice 1/3/5.
- Akzeptanzkriterium: Doku konsistent mit `auth.md`,
  `dependency-risk-register.md`, `security.md`; `npm run check`
  gruen.
- Bestand:
  - `auth.md` deckt Token-Header-Vertrag, Ticket-Flow,
    Frontend-Storage-Optionen.
  - `security.md` listet Phase 1/2/3 + P1 + Slice 3
    chronologisch.
  - `dependency-risk-register.md` haelt CVE-Baseline.
  - Code-Stand: `install_blueprint_guard()`, `token_required` mit
    `hmac.compare_digest`; CORS-Whitelist mit `AGORA_EXTRA_ORIGINS` und
    Wildcard-Optout `AGORA_CORS_ALLOW_ALL`; SSRF-Blocker
    `web_tools._is_public_url`; Vision-Cap `VISION_MAX_CALLS_PER_UPLOAD`;
    Label-Sanitizer `neo4j_mappings.sanitize_label`; Persona-Whitelist
    in `simulation_profiles.py`; Multi-Worker-safe Tickets via Redis
    (`signed_ticket.consume`); OASIS-Subprozess-Bridge
    (`subprocess_redis_bridge.py`).

## Vorgehen

1. Code-Snapshot bestaetigen (auth, web_tools, file_parser,
   neo4j_mappings, signed_ticket, simulation_runner Subprocess-Surface)
   damit das Threat-Model konkret bleibt und nicht generischen
   OWASP-Boilerplate produziert.
2. `docs/security-threat-model.md` strukturiert:
   - **Asset-Tabelle**: 10 Eintraege (Neo4j-Daten, Uploads, Reports,
     OASIS-Artefakte, Auth-Token, Tickets, `SECRET_KEY`, Neo4j-Passwort,
     HF-Cache, Logs) mit Sensitivitaet, Persistenz-Ort und Begruendung.
   - **Trust-Boundaries**: ASCII-Diagramm + sechs nummerierte Boundaries
     (B0–B5) inkl. Kontroll-Spalte je Boundary.
   - **Angreifer-Modelle**: sechs durchnummeriert (A1 untrusted
     LAN/Tailnet, A2 XSS/Plugin, A3 Supply-Chain, A4 geleakter Token,
     A5 boesartiges Upload, A6 SSRF). Pro Modell: Kontext, was er
     versucht, aktive Mitigations, Restrisiko.
   - **Top-5-Restrisiken**: kein echtes AuthN/AuthZ, keine
     Secrets-Rotation, OASIS-Subprozess-Vertrauen, Prompt-Injection im
     Quelldokument, Browser-Token-Storage.
   - **Out-of-Scope**: Multi-Tenant, Container-Escape, Physzugriff, DDoS,
     OS-Hijack — bewusst expliziert, damit das Modell nicht falsche
     Versprechen macht.
   - **Mitigation-Mapping-Tabelle**: zehn Threats → Slice/Phase →
     konkrete Datei. Schliesst die Lücke zwischen
     „Phasen-Chronologie in `security.md`“ und
     „Threat-zentrierter Sicht“.
   - **Review-Pflichten**: fünf Trigger, die das Modell anfassen muessen
     (Boundary-Code-Edit, neue Outbound-Quelle, neuer Secrets-Pfad,
     neue Dependency, API-Schema-Change).
3. Verweise auf bestehende Dokumente am Kopf und in den jeweiligen
   Mitigation-Bloecken (auth.md, security.md,
   dependency-risk-register.md, deployment-prod.md). Kein
   Duplikat-Content — das Threat-Model verlinkt, wo die Phasen-Doku
   schon Tiefe hat.
4. CHANGELOG `[Unreleased] › Docs` um Slice-8-Block ergaenzt (Konvention
   aus Slice 7).
5. Dieses Arbeitsprotokoll geschrieben.
6. `npm run check` als Gate, danach Commit + PR + Merge.

## Geaenderte / neue Dateien

| Datei | Aktion | LOC ca. |
|---|---|---|
| `docs/security-threat-model.md` | neu | 240 |
| `CHANGELOG.md` | edit (`[Unreleased]` → neuer Slice-8-Block oben unter `### Docs`) | +2 |
| `docs/2026-05-01-slice-8-threat-model-arbeitsprotokoll.md` | neu | dieses File |

## Verifikation

- `npm run check` — Doku-only-Slice darf den Gate nicht roetlich faerben.
- Boundary-Tabelle (B0–B5) gegen `backend/app/__init__.py`,
  `backend/app/utils/auth.py`, `docker-compose.yml`,
  `docker-compose.prod.yml`, `backend/app/services/web_tools.py`,
  `backend/app/services/simulation_runner.py` abgeglichen — die genannten
  Mechanismen entsprechen dem Code-Stand.
- Mitigation-Mapping verlinkt nur Dateien/Slices, die tatsaechlich im
  Repo existieren (Cross-Check via `git ls-files docs/` fuer
  Doku-Eintraege, `find backend/app -name '...'` fuer Code-Pfade).

## Akzeptanzkriterien (laut Plan)

- [x] `docs/security-threat-model.md` existiert.
- [x] Doku konsistent mit `auth.md`, `dependency-risk-register.md`,
      `security.md` (Verweise + Mitigation-Mapping).
- [ ] `npm run check` gruen — pending bis zum tatsaechlichen Lauf.

## Issue / Milestone

- F2 ist Folge-Plan, kein offenes GitHub-Issue mit `Closes #N`.
- Milestone: Repo-Review-Folge, kein expliziter Counter.

## Followups

- F3 — Operations + Backup/Restore.
- F4 — Release-Process.
- F5 — Test-Coverage-Luecken (SSRF, Upload, Cypher-Sanitizer; explizit
  als Test-Folgearbeit im Threat-Model unter A5 und A6 verankert).
- F6 — Branch-Cleanup + README-Update.

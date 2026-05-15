# Agora: Migrationsplan Bun/Python/Rust

> Basierend auf `agora-bun-rust-bewertung.md` und `agora-lohnt-sich-bun-rust.md`
> Ziel: pragmatischer Hybrid-Umbau, **kompletter Rewrite wird explizit vermieden**.
> Alle Änderungen bleiben **lokal** im Workspace.

---

## Aktueller Stand (2025-05-15)

| Phase | Status | Ergebnis |
|---|---|---|
| 1: Provider-Registry | ✅ Abgeschlossen | `app.core.provider_registry` + `app.core.config` Facades |
| 2: Frontend → Bun | ✅ Abgeschlossen | Dockerfile, package.json, bun.lock – alles auf Bun |
| 3: Backend modularisieren | 🔄 In Arbeit | `app.graph/` Facade steht, Worker & Router fehlen |
| 4: API-Gateway (optional) | ⏳ Ausstehend | Noch nicht begonnen |
| 5: Rust-Hotspots (optional) | ⏳ Ausstehend | Noch nicht begonnen |

**Zuletzt aktualisiert:** 15. Mai 2025 – Phase 3 teilweise (GraphRAG-Facade), Phase 1+2 komplett.

---

## Ausgangslage (IST)

```
agora/
├── frontend/          # Vue 3 + Vite + npm + package-lock.json
│   ├── package.json   # npm scripts (dev, build, test, lint)
│   └── src/           # Vue-Komponenten, Pinia, D3, Router
├── backend/           # Python (Flask/FastAPI) + uv + pyproject.toml
│   ├── app/           # Backend-Code
│   ├── scripts/       # Hilfsskripte
│   └── tests/         # Pytest
├── package.json       # Root: concurrently, npm scripts für dev/build
├── deploy/            # Docker, Compose, Infra
└── docu/              # Dokumentation
```

**Kernproblem:** Frontend hängt an `npm` (langsamer, mehr Reibung), Backend wächst monolithisch, LLM-Provider-Integrationen sind nicht zentralisiert.

---

## Zielbild (SOLL)

```
agora/
├── frontend/          # Bun + Vite + Vue 3 (beibehalten, Runtime tauschen)
├── api-gateway/       # NEU: Bun-basiertes Gateway (optional, Phase 4)
├── backend/           # Python Core modularisiert
│   ├── app/
│   │   ├── api/       # FastAPI-Router sauber getrennt
│   │   ├── core/      # LLM-Orchestrierung, Provider-Registry
│   │   ├── graph/     # Neo4j, GraphRAG-Pipeline
│   │   ├── workers/   # Langlaufende Jobs, Queues (RQ/Celery)
│   │   └── models/    # Pydantic-Modelle als Vertrag
│   └── tests/
├── rust-core/         # OPTIONAL: erst nach Profiling (Phase 5)
│   └── Cargo.toml     # Maturin/PyO3 für Python-Bridge
├── docker-compose.yml # Alle Services definiert
└── docs/
```

---

## Phase 1: Vorbereitung & Provider-Registry (Tag 1–2) ✅

**Ziel:** Saubere Abstraktion für LLM-Provider, Pydantic-Modelle, stabile API-Verträge.

| Schritt | Dateien / Befehle | Check |
|---|---|---|
| 1.1 | `backend/app/core/provider_registry.py` anlegen – Facade über `services/llm_provider_registry.py` | ✅ |
| 1.2 | `backend/app/models/` mit Pydantic v2 als zentrales Schema-Verzeichnis | ✅ bereits vorhanden |
| 1.3 | `backend/app/core/config.py` – Facade über `settings.py` + `config.py` (85 Abhängigkeiten → kein Move) | ✅ |
| 1.4 | Tests auf `app.core.*` migriert (`test_llm_core_services`, `test_github_copilot_provider`) | ✅ |
| 1.5 | `uv run pytest` grün — 2194 passed, 4 pre-existing failures (Defaults-Tests) | ✅ |

**Deliverable:** Backend kann alle LLM-Provider über eine einheitliche Registry ansprechen.

---

## Phase 2: Frontend auf Bun migrieren (Tag 2–3) ✅

**Ziel:** `npm` → `bun`, alle Scripts behalten, Build schneller.

| Schritt | Dateien / Befehle | Check |
|---|---|---|
| 2.1 | `cd frontend && rm package-lock.json` | ✅ |
| 2.2 | `bun install` – alle `dependencies` & `devDependencies` übernehmen | ✅ |
| 2.3 | `bun.lock` erzeugt, `package-lock.json` ist weg | ✅ |
| 2.4 | Scripts in `frontend/package.json` auf `bun` umstellen:<br>`"check": "bun run typecheck && bun run test:coverage && bun run build"` | ✅ |
| 2.5 | `frontend/vite.config.js` prüfen – kein npm-spezifischer Hack | ✅ |
| 2.6 | Root-`package.json` anpassen:<br>`"frontend": "cd frontend && bun run dev"`, `"setup": "bun install && cd frontend && bun install"` | ✅ |
| 2.7 | `bun run build` + `bun run test` erfolgreich | ✅ |
| 2.8 | Dockerfile: `npm ci` → `bun install --frozen-lockfile`, CMD `bun run dev` | ✅ |
| 2.9 | Playwright-Tests laufen weiter (`bunx playwright test`) | ✅ |

**Deliverable:** Frontend läuft vollständig auf Bun, Build < 5s, Tests grün.

**Geänderte Dateien:** `Dockerfile`, `package.json`, `frontend/package.json`, `bun.lock` (neu), `frontend/bun.lock` (neu), `package-lock.json` (gelöscht), `frontend/package-lock.json` (gelöscht).

---

## Phase 3: Backend modularisieren & API-Gateway vorbereiten (Tag 3–5) 🔄

**Ziel:** Monolith aufteilen, klare Service-Grenzen, Worker-Queue.

| Schritt | Dateien / Befehle | Check |
|---|---|---|
| 3.1 | `backend/app/api/` – Router-Module: `agents.py`, `graphs.py`, `providers.py`, `reports.py` | ⬜ |
| 3.2 | `backend/app/core/` – LLM-Client, Retry/Timeout-Logik, Circuit-Breaker-Muster | ⬜ |
| 3.3 | `backend/app/workers/` – RQ oder Celery-Tasks für lange Jobs (z.B. Graph-Aufbau, Report-Gen) | ⬜ |
| 3.4 | `backend/app/graph/` – Neo4j-Treiber, Cypher-Builder, GraphRAG-Pipeline | ✅ Facade erstellt |
| 3.5 | `backend/app/main.py` (FastAPI) importiert nur noch Router, keine Business-Logik | ⬜ |
| 3.6 | `docker-compose.yml` erweitern: Redis für Queue, Worker-Container | ⬜ |
| 3.7 | `uv run pytest` + `uv run ruff check` grün | ⬜ |

**Deliverable:** Backend ist modular, API-Gateway kann theoretisch vor Python gesetzt werden.

**Bisher erledigt:** `app/graph/__init__.py` – re-exportiert DTOs, Reader-Funktionen und InsightForge aus `services/graph/`.

---

## Phase 4: Optionales Bun API-Gateway (Tag 5–6, wenn gewünscht) ⏳

**Ziel:** Leichter Proxy/Gateway vor Python, schnelle Auth/Config-Endpoints.

| Schritt | Dateien / Befehle | Check |
|---|---|---|
| 4.1 | `api-gateway/` anlegen mit `package.json` (Bun) | ⬜ |
| 4.2 | `api-gateway/src/index.ts` – Elysia oder Hono als leichter Proxy | ⬜ |
| 4.3 | Routen: `/api/*` → Python-Backend, `/health` → Gateway selbst, `/config` → Modelllisten | ⬜ |
| 4.4 | `docker-compose.yml` um `api-gateway`-Service erweitern | ⬜ |
| 4.5 | `bun run dev` startet Gateway auf :3000, Backend auf :5000 | ⬜ |

**Deliverable:** Gateway ist optional, Frontend kann direkt oder über Gateway sprechen.

> **Hinweis:** Phase 4 ist *bedingt empfohlen*. Wenn Frontend direkt Python-Backend anspricht, überspringen.

---

## Phase 5: Profiling & Rust-Hotspots (Tag 6–10, **nur wenn nötig**) ⏳

**Ziel:** Nicht blind Rust einbauen, sondern messen, dann auslagern.

| Schritt | Dateien / Befehle | Check |
|---|---|---|
| 5.1 | `python -m cProfile -o profile.out -m backend.app` oder `py-spy` / `scalene` | ⬜ |
| 5.2 | Top-3 CPU-Bremser identifizieren (typisch: PDF-Parsing, Chunking, Deduplizierung) | ⬜ |
| 5.3 | Wenn Parsing/Chunking > 30% CPU: `rust-core/` mit `Cargo.toml` + `maturin` | ⬜ |
| 5.4 | Rust-Modul über PyO3 als `agora_rust` importierbar machen | ⬜ |
| 5.5 | Python-Code ruft `agora_rust.chunk(text)` oder `agora_rust.parse_pdf(...)` auf | ⬜ |
| 5.6 | Benchmark vorher/nachher: `uv run pytest tests/benchmark_chunking.py` | ⬜ |

**Rust-Kandidaten (nur wenn Profiling bestätigt):**

- `rust-core/src/chunking.rs` – Paralleles Chunking großer Dokumente
- `rust-core/src/parser.rs` – PDF/Text-Normalisierung
- `rust-core/src/dedup.rs` – Deduplizierung mit Hashing
- `rust-core/src/scoring.rs` – CPU-lastiges Ranking/Scoring

**Deliverable:** Messbarer Performance-Gewinn durch Rust, nicht Spekulation.

---

## Gesamt-Zeitplan

| Phase | Dauer | Investition | Status |
|---|---|---|---|
| 1: Provider-Registry | 1–2 Tage | Sehr hoch | ✅ Fertig |
| 2: Frontend → Bun | 1–2 Tage | Hoch | ✅ Fertig |
| 3: Backend modularisieren | 2–3 Tage | Sehr hoch | 🔄 Teilweise |
| 4: API-Gateway (optional) | 1 Tag | Mittel | ⏳ Ausstehend |
| 5: Rust-Hotspots (optional) | 2–4 Tage | Später | ⏳ Ausstehend |

**Gesamt:** Phase 1+2 komplett, Phase 3 zu ~15% (Graph-Fassade). Kern stabil.

---

## Lokal-Regeln (hart)

- Alle Änderungen in PRs mit Review – kein direkter Push auf `main`.
- `package-lock.json` wird gelöscht, `bun.lock` ist der neue Source of Truth.
- Bun-Version: `>=1.0.0` (siehe `engines` in `package.json`).
- Rust nur anlegen, wenn `profile.out` es rechtfertigt.
- Docker: `oven/bun:1` als COPY-From-Stage, kein separates Node-Image mehr.

---

## Risiken & Gegenmaßnahmen

| Risiko | Gegenmaßnahme |
|---|---|
| Bun nicht 100% kompatibel mit Vite/Vue | Schritt 2.7 + 2.8: Build & Tests müssen grün sein ✅ |
| Python-Module kreuzimportieren sich | Schritt 3.5: `main.py` darf nur Router importieren |
| Worker-Queue überflüssig | Schritt 3.3 nur umsetzen, wenn lange Jobs existieren |
| Rust-Bridge zu komplex | Schritt 5.3: Maturin-Template nutzen, klein anfangen |
| Zeitplan zu optimistisch | Phase 4 & 5 sind optional – Kern ist nach Phase 3 stabil |
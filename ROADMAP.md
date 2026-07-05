# Agora Roadmap

> Stand: 2026-07-05 (post M3-Port, v1.0.0). Strategische Prioritäten — ausführbare Tasks liegen als GitHub-Issues, ausgelieferte Änderungen im [`CHANGELOG.md`](CHANGELOG.md), operative Slice-Planung in [`PLAN.md`](PLAN.md), Test-Counts/Layer-Status in [`docs/STATUS.md`](docs/STATUS.md). Layer-Detailtabelle: [`CLAUDE.md`](CLAUDE.md#architektur-layer-status). Subagent-Mapping pro Slice: lokal in `docs/.local/archive/plans/plan.heuristic.md` (gitignored). Versions-Historie: [`docs/refactoring-backlog.md`](docs/refactoring-backlog.md), [`CHANGELOG.md`](CHANGELOG.md).

## Verbindliche Trennung

| Dokument | Rolle |
|---|---|
| `ROADMAP.md` (diese Datei) | Strategische Prioritäten (Now / Next / Later) |
| GitHub Issues | Ausführbare Tasks, mit Acceptance + Owner |
| [`CHANGELOG.md`](CHANGELOG.md) | Bereits ausgelieferte Änderungen |
| [`docs/STATUS.md`](docs/STATUS.md) | Auto-generiert (Versions-/Test-Counts), CI-enforced via `scripts/sync-status.sh --check` |
| [`PLAN.md`](PLAN.md) | Operativer Slice-Plan (laufende Wellen, Phasen) |

## Current State (v1.0.0, 2026-05-11; Layer 0–6 + 9–10 grün, 7–8 teilweise)

Lokal-first Multi-Agent-Simulator für DACH-Zielgruppenreaktionen auf Neo4j CE + Ollama. Pipeline end-to-end: Upload → Wissensgraph → Personas → OASIS-Simulation → DACH-Report. **M3-Port — Unified Provider Abstraction** abgeschlossen (PR #666, 2026-07-05); Provider-Detection-SSoT: `backend/app/llm/providers/registry.py::detect_provider(mode="http"|"oasis")`.

---

## Now / Next / Later

### Now — M3-Port Follow-ups + Hardstop-Fristen (Juli 2026)

- **Phase F — Rest-Detection-Delegation** (je eigener PR, TDD): #669 (`simulation_lifecycle._detect_default_provider` → `registry.detect_provider(mode="http")`), #670 (`_sim_common._is_ollama_route` think/num_ctx-Gate für `ollama.com`), #671 (`embedding_service._detect_provider` vereinheitlichen ODER bewusst separat dokumentieren).
- **Dependency-Hardstops** ([`docs/dependency-risk-register.md`](docs/dependency-risk-register.md)): `nltk` PYSEC-2026-597 + GHSA-p4gq-832x-fm9v → **2026-07-30**; Trivy OS-Layer CVE-2026-24049/23949 → **2026-08-30**. Tracking-Issues #661, #672.
- **v1.0-Output-Vertrag** ([`PLAN.md`](PLAN.md)) — offen: P3.2, P4.1, P4.3, P4.4.
- **Design Language v4 — App-Shell-Port:** Integration-Branch `feat/design-v4-epic`, Slices A–E durch, F läuft. Vendoriert in [`design/v3-source/`](design/v3-source/).
- **Observability Slice 1 — End-to-End-Tracing** (Plan abgenommen, Implementation offen): [`docs/plans/active/`](docs/plans/active/).

### Next — Stabilisierung & Coverage härten (August 2026)

- Evidence-Gate hard (ADR-0002-Anker unangetastet), Backend-/Frontend-Coverage-Gates, Playwright-Smokes für die Kern-Pipeline (Upload → Graph → Persona → Simulation → Report).
- v1.0-Output-Vertrag-Arbeitspakete P3.2/P4.1/P4.3/P4.4 ausliefern.
- Design Language v4 Slice F abschließen und auf `main` mergen.

### Later — v1.x Skalierung (Q3/Q4 2026)

- Helm-Chart, Performance-Benchmarks (Throughput/Latenz pro Hardware-Tier), Federation-Groundwork (mehrere Agora-Instanzen teilen Entitätswissen).
- Plugin-System für Custom-NER, Search-Strategien, Report-Templates.
- Graph-Versioning (Snapshots), Branch-Compare-UI, Replay/Reproduce-Run.

---

## Hardware Tiers

| Tier | RAM | GPU VRAM | Empfohlenes Modell | Performance |
|---|---|---|---|---|
| Minimal | 8 GB | — (CPU) | `qwen2.5:3b` | Langsam, basics NER |
| Light | 16 GB | 6–8 GB | `qwen2.5:7b` | Kleine Graphen nutzbar |
| Standard | 32 GB | 12–16 GB | `qwen2.5:14b` | Gut für die meisten Fälle |
| Power | 64 GB | 24+ GB | `qwen3-coder:cloud` (Ollama Cloud) oder `qwen2.5:32b` lokal | Vollqualität, schnell |

---

## Historie

- **v1.0.0 (2026-05-11):** Layer 0–6 grün, 7–8 teilweise, 9–10 grün. M11 Phase 1–5b durch.
- **M3-Port (2026-07-05, PR #666):** Unified Provider Abstraction + Detection. Schließt #590, #591, #582, #636.
- **Security-Wellen (2026-07):** `transformers>=5.3.0` (CVE-2026-4372/1839, PYSEC-2025-217), `nltk==3.9.4` risk exception (PYSEC-2026-597, GHSA-p4gq-832x-fm9v), `torch==2.12.1` (PYSEC-2026-139), `pillow==12.2.0`, `pytest==9.0.3`, `unstructured>=0.18.18`. Siehe [`docs/dependency-risk-register.md`](docs/dependency-risk-register.md).
- **0.5 / 0.6 / 0.7 / 0.8 Linien:** Reader-Honesty-Refactor, Frontend-TS-Migration, M9 Prod-Hardening (Reverse-Proxy-Sidecar, Gunicorn gevent, Bundle-Token-Gate, signed tickets). Detail-Historie im [`CHANGELOG.md`](CHANGELOG.md).

---

## Contributing

AGPL-3.0. Siehe [`CONTRIBUTING.md`](CONTRIBUTING.md) und [GitHub Issues](https://github.com/arn0ld87/agora/issues) für aktive Arbeit.
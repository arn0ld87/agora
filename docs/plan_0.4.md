 # Agora v0.4.0 — Operability-First Stability Release

  ## Summary

  0.4.0 should be a small, shippable stability release focused on making Agora easier to operate, diagnose, and trust in day-to-day local use.
  Based on the current repo state, the right scope is:

  - promote the existing partial health/model checks into a real unified status surface,
  - add structured logging as an opt-in operational mode,
  - improve deployment ergonomics around Docker/GPU detection,
  - add Neo4j connection resilience where failures are currently too brittle,
  - explicitly defer Python 3.12 + CAMEL/OASIS compatibility to a follow-up release.

  This keeps 0.4.0 coherent and avoids turning it into a dependency-upgrade project.

  ## Key Changes

  ### 1. Unified /api/status as the canonical ops endpoint

  Use the existing probes in backend/app/api/simulation.py:90 as the seed, but move to a dedicated top-level status endpoint.

  Behavior:

  - Return one consolidated payload for:
      - backend app health
      - Neo4j reachability
      - Ollama reachability
      - installed/available Ollama models
      - configured default model
      - disk usage for key writable paths
      - current auth mode / safe-to-expose flags if useful
  - Keep the response lightweight and synchronous.
  - Use clear booleans plus machine-readable error strings.
  - Make this the source for frontend “system readiness” indicators instead of scattered health assumptions.

  Public interface:

  - Add GET /api/status
  - Keep existing simulation-specific model listing behavior temporarily if the frontend still depends on it, but treat it as deprecated once /api/status is wired in.

  ### 2. Structured logging as opt-in, not replacement

  Extend backend/app/utils/logger.py:1 so text logs remain the default, but JSON logs are available via env/config.

  Behavior:

  - Add env toggle such as AGORA_LOG_FORMAT=text|json
  - JSON mode should include at least:
      - timestamp
      - level
      - logger
      - message
      - module/function/line
      - optional request or simulation identifiers when available
  - Keep current log files and rotation model.
  - Avoid changing all call sites; implement this mostly in formatter/setup code.
  - Preserve human-readable console output unless JSON is explicitly requested.

  Important implementation detail:

  - Do not try to redesign all logging in one pass.
  - Only add minimal context enrichment where IDs already exist naturally, especially around simulation runs and background tasks.

  ### 3. Docker/GPU readiness detection

  Add a pragmatic deployment check rather than over-engineered hardware orchestration.

  Behavior:

  - Detect at startup or via /api/status whether GPU acceleration is likely available for Ollama usage.
  - Surface:
      - GPU visible / not visible
      - likely CPU-only mode
      - any obvious mismatch hints if detectable
  - Update docker-compose.yml and docs so CPU fallback is explicit and safe.

  Recommended scope:

  - Prefer a simple detect-and-report approach over dynamic container mutation.
  - If Compose GPU reservation is added, make it optional and documented, not mandatory.

  ### 4. Neo4j connection resilience

  Reduce hard failures caused by transient Neo4j unavailability, especially around startup and long-running usage.

  Behavior:

  - Keep fail-fast semantics where startup must know Neo4j is absent, but add retry/reconnect behavior for transient runtime failures in the storage layer.
  - Reuse existing retry patterns in Neo4jStorage instead of inventing a parallel mechanism.
  - Ensure /api/status reflects degraded Neo4j state clearly if the driver is unavailable or reconnecting.

  Implementation target:

  - Tighten resilience in the storage/connection boundary, not across every API endpoint individually.

  ### 5. Release discipline for 0.4.0

  Do not include Python 3.12 compatibility work in the implementation scope of 0.4.0.

  Release notes / roadmap adjustments:

  - Mark Python 3.12 + CAMEL/OASIS as explicitly deferred.
  - Position 0.4.0 as “operability and resilience”.
  - Move Python-compatibility work into 0.4.1 or 0.5, depending on how dependency risk looks after investigation.

  ## Test Plan

  ### Status endpoint

  - GET /api/status returns success payload with all expected sections.
  - Neo4j down: endpoint still responds, marks Neo4j unreachable, includes error.
  - Ollama down: endpoint still responds, marks Ollama unreachable, includes error.
  - Disk usage fields are present and sane on a normal local install.

  ### Structured logging

  - Default env: logs remain text and existing log flow still works.
  - JSON mode: each line is valid JSON and contains required fields.
  - Simulation/background-run logs still rotate and remain readable by current tooling.

  ### Docker / GPU behavior

  - CPU-only environment reports CPU fallback cleanly.
  - GPU-capable environment reports acceleration availability without breaking CPU users.
  - Compose/docs path remains runnable for users without NVIDIA runtime.

  ### Neo4j resilience

  - Simulated transient Neo4j failure does not permanently poison the process if recovery is possible.
  - Recovered Neo4j connection is reflected in status checks.
  - Permanent failure still surfaces clear errors rather than silent degradation.

  ### Regression checks

  - Existing frontend readiness indicators still function after switching to /api/status.
  - Graph build, simulation start, and report generation still work in the normal happy path.
  - No new duplicate logs or logging-format regressions in simulation subprocess flows.

  ## Assumptions

  - 0.4.0 is a tight release, not a “finish every roadmap bullet” milestone.
  - The current partial health/model probe in simulation.py is good enough to reuse rather than rewrite from scratch.
  - Python 3.12 compatibility is intentionally out of scope for 0.4.0.
  - Context7 is not available in this session, so this plan is grounded in the checked-in code and current repo structure rather than live MCP doc lookups.

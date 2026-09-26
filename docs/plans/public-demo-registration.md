# Public Agora demo: registration and workspace credentials

## Goal

An external visitor can register with email and password, confirm their email,
sign in without an Agora master token, enter their own provider credentials, and
run Agora in a workspace isolated from every other visitor and the operator.

## Verified starting point (26 September 2026)

- The frontend already has registration, confirmation, login, and Supabase JWT
  request headers. The running Agora returns `jwt_enabled: false` from
  `/api/auth/config`, so the browser currently falls back to the legacy token.
- The running `/opt/supabase` Auth project is shared with AP1. Its site URL is
  AP1 and email auto-confirmation is enabled. Agora must use its own Auth
  project; changing the shared project would change AP1's login behavior.
- The committed `supabase/` stack is named `agora-supabase` but is not running.
  Agora's five metadata repositories already use PostgreSQL on the server.
- Provider connections and encrypted keys are global. `/api/llm` and settings
  are operator-only for JWT users. Exposing those APIs as-is would share
  credentials and routing state between visitors.
- `agora.alexle135.de` resolves to a Tailnet address and its Traefik router
  uses `tswebsecure` only.

## Ordered slices

1. **Credential contract and storage.** Add a workspace-scoped Pydantic API
   contract, encrypted persistence, and ownership checks. Never return key
   material, and never fall back to an operator key for a JWT principal.
   Acceptance: workspace A cannot read, overwrite, or use workspace B's key;
   a missing key fails closed.
2. **Runtime routing.** Make every external LLM and embedding call resolve the
   key for the run's workspace, including background jobs and subprocesses.
   Acceptance: representative graph, prepare, simulation, and report paths use
   the expected workspace credential; no key appears in run artifacts or logs.
3. **Visitor UI.** Add a workspace provider settings view that uses the new
   contract and shows only configured/not configured state. Keep operator
   settings restricted. Acceptance: a confirmed user can add, replace,
   and delete their own key without using the browser console or master token.
4. **Dedicated demo stack.** Deploy Agora with isolated metadata, artifacts,
   Neo4j, Redis, and the committed `agora-supabase` stack with its own Auth
   database and issuer, email confirmation, production SMTP,
   redirect allow-list, and abuse controls. Set Agora's JWT configuration.
   Acceptance: registration sends mail; no session is issued before the mail
   is confirmed; login then yields `jwt_enabled: true` and a personal workspace.
5. **Public ingress.** Publish Agora and only the required Supabase gateway
   paths over HTTPS; preserve private database, Studio, and operator access.
   Change DNS after the external smoke tests pass. Acceptance: an external
   browser can complete registration and a run; anonymous API calls fail.

## Release gates

- Contract and schema checks, targeted backend and frontend tests, lint/type
  checks, and the applicable pre-push gate pass on a dedicated branch.
- Test cross-workspace access, global provider-key fallback, unconfirmed email,
  token-less API access, signup abuse limits, and external redirect handling.
- Back up PostgreSQL and Agora artifacts before migration and deployment.
- Keep the public DNS and route private until every gate above is green.
- ADR-0019 expressly defers production multi-user use until after 1.0. The
  owner must choose and document a demo exception before public exposure.

## Risk

High complexity: provider configuration, runtime resolution, async jobs, and
deployment cross trust boundaries. The auth UI alone does not make Agora safe
for public registration.

# FE-Redesign Slice 5-pre — Backend: PostCreatedEvent + OASIS-Emit

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Die SSE-Pipeline um Post-Events erweitern, damit Slice 5 (Frontend Sim-Feed Dual-Column) auf einen echten Live-Stream zugreifen kann. Heute liefert SSE nur SimulationRunState (laufender/pausiert/etc.); konkrete Post-Aktionen aus OASIS landen im Action-Log und SQLite, aber nicht als Stream-Frame im Frontend.

**Architecture:** Neuer Pydantic-Contract `PostCreatedEvent` (Layer 0, `extra="forbid"`). OASIS-Runner emittiert nach jedem `CREATE_POST` einen entsprechenden Frame via `event_bus` an Redis-pub/sub. `simulation_stream.py` reicht Post-Events durch SSE durch. Zod-Spiegel im Frontend. Slice 5 konsumiert via `useEventStream`.

**Tech Stack:** Python 3.11, Pydantic v2, Flask + gevent SSE, Redis-pub/sub (subprocess_redis_bridge), Zod 4, vue-router 5.

**Spec-Quelle:** [`docs/plans/2026-05-15-frontend-redesign-shadcn-feel.md`](2026-05-15-frontend-redesign-shadcn-feel.md), Section "Slice 5" + offene Frage 1.

**Audit-Quelle:** Slice-5-Vorklärung (Explore-Agent, 2026-05-15) — Befund: `platform`, `parent_post_id`, `post_id`, `persona_id`, `voice_register` fehlen im SSE-Frame; werden teils in SQLite-Post-Tabelle / Action-Log emittiert, aber nicht weitergereicht.

**Worktree:** `/private/tmp/agora-fe-redesign-5-pre` (Lead legt vor Dispatch an, Branch `feat/fe-redesign-5-pre-post-event` basiert auf `feat/fe-redesign-epic`).
**Push-Verbot:** KEIN Push, KEIN PR. Slice landet später im Integration-Branch des Epics.

**Layer-Reihenfolge-Check:** Layer 0 (Pydantic-Contract) → Layer 1 (event_bus + simulation_stream) → Layer 4 (Zod-Spiegel + useEventStream-Typ). Layer-aufwärts.

**Subagent:** `agora-refactor-worker` (Python-Layer-0-Touch + Service-Refactor) + im Schluss `agora-frontend-worker` für Zod-Spiegel und `useEventStream`-Type-Update.

---

## File Structure

**Create:**
- `backend/app/contracts/post_event_contract.py` — Pydantic-Contract `PostCreatedEvent` + Enum `Platform`.
- `backend/tests/contracts/test_post_event_contract.py` — Contract-Tests (`extra="forbid"`, Enum-Werte, Pflichtfelder).
- `backend/tests/api/test_simulation_stream_post_event.py` — SSE-Smoke: PostCreatedEvent geht durch.
- `frontend/src/contracts/postEventContract.ts` — Zod-Spiegel.
- `frontend/src/contracts/__tests__/postEventContract.spec.ts` — Spiegel-Test gegen JSON-Schema.

**Modify:**
- `backend/app/services/event_bus.py` — `SimulationEvent.payload` darf typisiert `PostCreatedEvent` enthalten (oder Event-Typ als Discriminator).
- `backend/app/api/simulation_stream.py` — `_event_to_sse` reicht Post-Event-Frames durch, mit `event: post_created`-SSE-Field.
- `backend/scripts/run_parallel_simulation.py` — nach `CREATE_POST` Action: `event_bus.emit_post_created(...)` aufrufen (oder analoge Bridge in `subprocess_redis_bridge.py`).
- `backend/scripts/subprocess_redis_bridge.py` — Bridge-Pfad für Post-Events ergänzen, falls separater Channel nötig.
- `schemas/` — auto-generiert via `python -m app.contracts.dump_schemas`.
- `frontend/src/api/stream.ts` — `SseEventFrame`-Type um Post-Event-Variante erweitern.
- `frontend/src/composables/useEventStream.ts` — Type-Sichere Filterung nach Event-Typ.

**Do NOT touch:**
- OASIS-CAMEL-Internals (`camel-oasis`-Submodul). Wir greifen die Action vor dem Persist ab, nicht im CAMEL-Eventloop.
- Slice-5-Frontend-Komponenten (`v4/sim-feed/`) — eigener Slice.
- ReportV3 / Persona-Quoten / Confidence — andere Layer.

---

## Pre-Flight

- [ ] **Step 0.1: Worktree-Check**

```bash
cd /private/tmp/agora-fe-redesign-5-pre
git branch --show-current
test -L frontend/node_modules && echo OK_fe || echo FEHLT_fe
# Backend uses uv directly, kein Symlink nötig
cd backend && uv sync --group dev > /dev/null && echo "uv ok"
```
Expected: Branch `feat/fe-redesign-5-pre-post-event`, FE-Symlink ok, uv sync exit 0.

- [ ] **Step 0.2: Baseline grün**

```bash
cd /private/tmp/agora-fe-redesign-5-pre/backend
uv run pytest tests/contracts/ -q
uv run pytest tests/api/ -q
uv run ruff check app && uv run mypy app
cd ../frontend
bun run typecheck && bun test -- --run src/contracts/
```
Expected: alle exit 0. Falls rot → STOP, an Lead.

- [ ] **Step 0.3: Audit-Anker lesen** (Bestätigung der Vorklärung)

```bash
sed -n '57,83p' backend/app/services/event_bus.py
sed -n '68,82p' backend/app/api/simulation_stream.py
sed -n '680,720p' backend/scripts/run_parallel_simulation.py
sed -n '27,40p' frontend/src/api/stream.ts
```
Notiere konkrete Zeilennummern für `SimulationEvent`, `_event_to_sse`, `CREATE_POST`-Handler, `SseEventFrame`. Plan-Tasks unten referenzieren diese.

---

## Task 1: Test-First — PostCreatedEvent Contract (RED)

**Files:**
- Create: `backend/tests/contracts/test_post_event_contract.py`

- [ ] **Step 1.1: Test-Datei anlegen**

Create `backend/tests/contracts/test_post_event_contract.py`:

```python
"""Contract-Tests für PostCreatedEvent.

Layer 0 — Single Source of Truth. extra="forbid", Enum-Werte hart,
Pflichtfelder hart.
"""

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.contracts.post_event_contract import (
    Platform,
    PostCreatedEvent,
)


def _valid_payload() -> dict:
    return {
        "event_type": "post_created",
        "simulation_id": "sim-123",
        "post_id": "post-abc",
        "parent_post_id": None,
        "platform": "reddit",
        "persona_id": "persona-7",
        "voice_register": "casual",
        "is_simulated": True,
        "body": "Mein erster Post.",
        "timestamp": datetime(2026, 5, 15, 12, 0, tzinfo=timezone.utc).isoformat(),
    }


class TestPostCreatedEvent:
    def test_accepts_valid_payload(self) -> None:
        ev = PostCreatedEvent.model_validate(_valid_payload())
        assert ev.platform is Platform.REDDIT
        assert ev.parent_post_id is None
        assert ev.is_simulated is True

    def test_rejects_unknown_field(self) -> None:
        payload = _valid_payload()
        payload["new_field"] = "x"
        with pytest.raises(ValidationError):
            PostCreatedEvent.model_validate(payload)

    def test_rejects_unknown_platform(self) -> None:
        payload = _valid_payload()
        payload["platform"] = "mastodon"
        with pytest.raises(ValidationError):
            PostCreatedEvent.model_validate(payload)

    def test_parent_post_id_allowed_for_reddit(self) -> None:
        payload = _valid_payload()
        payload["parent_post_id"] = "post-parent"
        ev = PostCreatedEvent.model_validate(payload)
        assert ev.parent_post_id == "post-parent"

    def test_voice_register_required(self) -> None:
        payload = _valid_payload()
        del payload["voice_register"]
        with pytest.raises(ValidationError):
            PostCreatedEvent.model_validate(payload)

    def test_is_simulated_default_true(self) -> None:
        payload = _valid_payload()
        del payload["is_simulated"]
        ev = PostCreatedEvent.model_validate(payload)
        assert ev.is_simulated is True

    def test_event_type_literal_post_created(self) -> None:
        payload = _valid_payload()
        payload["event_type"] = "wrong"
        with pytest.raises(ValidationError):
            PostCreatedEvent.model_validate(payload)
```

- [ ] **Step 1.2: Tests rot laufen sehen**

```bash
cd /private/tmp/agora-fe-redesign-5-pre/backend
uv run pytest tests/contracts/test_post_event_contract.py -v
```
Expected: alle 7 Tests FAIL mit `ModuleNotFoundError: No module named 'app.contracts.post_event_contract'`.

- [ ] **Step 1.3: Commit "test(contracts): red — PostCreatedEvent"**

```bash
git add backend/tests/contracts/test_post_event_contract.py
git commit -m "$(cat <<'EOF'
test(contracts): red — PostCreatedEvent (platform/parent/voice/sim)

Layer 0 Contract-Tests vor Implementation. extra="forbid", Enum-Werte
hart, voice_register Pflicht, is_simulated default true.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: PostCreatedEvent Contract implementieren (GREEN)

**Files:**
- Create: `backend/app/contracts/post_event_contract.py`

- [ ] **Step 2.1: Contract schreiben**

Create `backend/app/contracts/post_event_contract.py`:

```python
"""PostCreatedEvent — Layer-0-Contract für Live-Sim-Feed.

Slice FE-Redesign-5-pre · 2026-05-15

Wird emittiert nach jedem CREATE_POST-Action im OASIS-Runner. Geht via
event_bus + simulation_stream als SSE-Frame `event: post_created` ans
Frontend. Slice 5 (Dual-Column Sim-Feed) konsumiert.

Wording-Glossar v1: `is_simulated=True` ist Pflicht-Marker für alle
OASIS-emittierten Posts. Frontend rendert SIM-Badge. Kein "prediction".
"""

from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Platform(str, Enum):
    """Plattform-Enum für Dual-Column-Routing.

    Eng halten — andere Channels (Mastodon, Threads) brauchen ADR + Slice.
    """

    REDDIT = "reddit"
    TWITTER = "twitter"


class VoiceRegister(str, Enum):
    """Voice-Register aus oasis_profile_generator (Sub-Slice 10).

    Frontend rendert Badge in PersonaAvatar.
    """

    FORMAL = "formal"
    CASUAL = "casual"
    JUGENDSPRACHE = "jugendsprache"


class PostCreatedEvent(BaseModel):
    """SSE-Frame für einen einzelnen Post-Action des OASIS-Runners."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    event_type: Literal["post_created"] = "post_created"
    simulation_id: str = Field(..., min_length=1)
    post_id: str = Field(..., min_length=1)
    parent_post_id: str | None = None
    platform: Platform
    persona_id: str = Field(..., min_length=1)
    voice_register: VoiceRegister
    is_simulated: bool = True
    body: str = Field(..., min_length=1)
    timestamp: datetime
```

- [ ] **Step 2.2: Tests grün**

```bash
uv run pytest tests/contracts/test_post_event_contract.py -v
```
Expected: alle 7 grün.

- [ ] **Step 2.3: Schemas regenerieren**

```bash
uv run python -m app.contracts.dump_schemas
git status schemas/
```
Expected: neue Datei `schemas/PostCreatedEvent.json` (oder erweiterte Sammeldatei je nach dump_schemas-Konvention).

- [ ] **Step 2.4: Commit**

```bash
git add backend/app/contracts/post_event_contract.py schemas/
git commit -m "$(cat <<'EOF'
feat(contracts): add PostCreatedEvent (Layer 0)

Slice 5-pre: SSE-Frame für Live-Sim-Feed Dual-Column-Routing.
Platform-Enum auf reddit/twitter, voice_register Pflicht, is_simulated
default true (Wording-Glossar v1).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: event_bus — emit_post_created

**Files:**
- Modify: `backend/app/services/event_bus.py`
- Create: `backend/tests/services/test_event_bus_post_created.py`

- [ ] **Step 3.1: Bestehende `event_bus.py` lesen** (Pre-Flight Step 0.3, Zeilen 57–83 — `SimulationEvent`-Envelope)

Notiere die existing `emit_*`-Methoden und das Redis-Channel-Naming.

- [ ] **Step 3.2: Test schreiben (RED)**

Create `backend/tests/services/test_event_bus_post_created.py` — mind. 3 Tests:
1. `emit_post_created` ruft Redis-pub auf mit korrektem Channel und JSON.
2. Payload validiert gegen `PostCreatedEvent` (kein leerer body, kein unknown field).
3. `simulation_id` wird im Redis-Channel-Namen verwendet (Multi-Tenant).

(Code-Block siehe analog Slice 1 Pattern — Worker schreibt aus existing event_bus-Test-Pattern ab.)

- [ ] **Step 3.3: `emit_post_created`-Methode implementieren** (GREEN)

In `event_bus.py` neue Methode hinzufügen:

```python
def emit_post_created(self, event: PostCreatedEvent) -> None:
    """Publish a PostCreatedEvent to the simulation-specific channel.

    Channel: agora:sim:{simulation_id}:post_created
    Body: event.model_dump_json()
    """
    channel = f"agora:sim:{event.simulation_id}:post_created"
    self._redis.publish(channel, event.model_dump_json())
```

(Genaue Integration in existing `EventBus`-Klasse + Pool — Worker passt an.)

- [ ] **Step 3.4: Tests grün + Commit**

---

## Task 4: SSE-Stream-Pfad — Post-Event-Frame durchreichen

**Files:**
- Modify: `backend/app/api/simulation_stream.py` (`_event_to_sse` + Subscribe-Loop)
- Create: `backend/tests/api/test_simulation_stream_post_event.py`

- [ ] **Step 4.1: Test schreiben (RED)**

Test (Skelett):

```python
def test_sse_emits_post_created_frame(client, redis_publisher):
    """E2E-Smoke: Redis-pub → SSE → Frame mit event: post_created."""
    sim_id = "sim-test-1"
    payload = PostCreatedEvent(
        simulation_id=sim_id,
        post_id="post-1",
        platform=Platform.REDDIT,
        persona_id="persona-x",
        voice_register=VoiceRegister.CASUAL,
        body="hi",
        timestamp=datetime.now(tz=timezone.utc),
    )

    # Subscribe via SSE, then publish, then read first frame
    with client.stream("/api/simulations/{}/events".format(sim_id)) as resp:
        redis_publisher.publish(
            f"agora:sim:{sim_id}:post_created",
            payload.model_dump_json(),
        )
        frame = next_sse_frame(resp)
        assert frame.event == "post_created"
        assert "post-1" in frame.data
```

(Worker passt an die echte Test-Infrastruktur an — vermutlich Fixtures `client`, `redis_publisher` schon vorhanden.)

- [ ] **Step 4.2: `_event_to_sse` erweitern**

In `simulation_stream.py`: Subscribe auf zusätzlichen Channel `agora:sim:{sim_id}:post_created`. Frame-Format:

```
event: post_created
data: {"event_type":"post_created","simulation_id":"...","post_id":"...",...}

```

(Leerzeile am Ende — SSE-Pflicht.)

Sicherstellen, dass das nicht den existing State-Frame-Path bricht. Beide Channels sollten parallel laufen (separater Multiplexer oder zweiter Subscribe).

- [ ] **Step 4.3: Tests grün + Commit**

---

## Task 5: OASIS-Runner — emit nach CREATE_POST

**Files:**
- Modify: `backend/scripts/run_parallel_simulation.py` (~ Zeilen 680–720 lt. Audit, exakt prüfen)

- [ ] **Step 5.1: CREATE_POST-Handler lokalisieren**

```bash
grep -n "CREATE_POST" backend/scripts/run_parallel_simulation.py
```

- [ ] **Step 5.2: Nach erfolgreichem Action-Persist `emit_post_created` aufrufen**

Pseudocode-Insert nach existing Post-Persist:

```python
from app.contracts.post_event_contract import PostCreatedEvent, Platform, VoiceRegister
from app.services.event_bus import event_bus

# ... nach existing CREATE_POST-Handling, post_row ist persistiert ...
event_bus.emit_post_created(PostCreatedEvent(
    simulation_id=simulation_id,
    post_id=post_row.id,
    parent_post_id=post_row.parent_post_id,
    platform=Platform(post_row.platform),
    persona_id=agent.persona_id,
    voice_register=VoiceRegister(agent.voice_register),
    is_simulated=True,
    body=post_row.body,
    timestamp=post_row.created_at,
))
```

> **Wichtig:** Im OASIS-Subprozess läuft `gevent.monkey.patch_all()` und Redis-IPC geht über `subprocess_redis_bridge`. Prüfen ob direkter `event_bus`-Call funktioniert oder ob die Bridge zwischengeschaltet werden muss (Audit ergab: subprocess_redis_bridge ist der Pfad). Falls Bridge-Pfad nötig: `emit_post_created` wird über die Bridge marshalled — eigener Sub-Schritt 5.2b.

- [ ] **Step 5.3: Smoke im Subprozess-Pfad**

Lokal:
```bash
cd /private/tmp/agora-fe-redesign-5-pre/backend
uv run pytest tests/services/test_subprocess_redis_bridge.py -v
```

Plus manuelle Smoke (kein automatisierter Test, wenn nicht trivial):
- Start lokale Sim mit Stub-Mode
- Beobachte Redis-pub auf `agora:sim:*:post_created` Channel
- Beobachte SSE-Frame im `curl /events`-Pfad

- [ ] **Step 5.4: Commit**

---

## Task 6: Zod-Spiegel + Frontend-Type-Sicherheit

**Files:**
- Create: `frontend/src/contracts/postEventContract.ts`
- Create: `frontend/src/contracts/__tests__/postEventContract.spec.ts`
- Modify: `frontend/src/api/stream.ts` (SseEventFrame-Type)
- Modify: `frontend/src/composables/useEventStream.ts` (Event-Type-Filter)

- [ ] **Step 6.1: Zod-Spiegel**

Create `frontend/src/contracts/postEventContract.ts`:

```typescript
import { z } from 'zod'

export const PlatformSchema = z.enum(['reddit', 'twitter'])
export type Platform = z.infer<typeof PlatformSchema>

export const VoiceRegisterSchema = z.enum(['formal', 'casual', 'jugendsprache'])
export type VoiceRegister = z.infer<typeof VoiceRegisterSchema>

export const PostCreatedEventSchema = z.object({
  event_type: z.literal('post_created'),
  simulation_id: z.string().min(1),
  post_id: z.string().min(1),
  parent_post_id: z.string().nullable(),
  platform: PlatformSchema,
  persona_id: z.string().min(1),
  voice_register: VoiceRegisterSchema,
  is_simulated: z.boolean().default(true),
  body: z.string().min(1),
  timestamp: z.string().datetime(),
}).strict()

export type PostCreatedEvent = z.infer<typeof PostCreatedEventSchema>
```

- [ ] **Step 6.2: Spec gegen JSON-Schema validieren**

Spec lädt `schemas/PostCreatedEvent.json` und prüft, dass alle Pydantic-Felder im Zod-Spiegel sind (Schema-Drift-Gate, analog Sub-Slice 02b/c).

- [ ] **Step 6.3: `useEventStream.ts` Type-erweitern**

```typescript
import { PostCreatedEventSchema, type PostCreatedEvent } from '@/contracts/postEventContract'

export type StreamEventFrame =
  | { event: 'state'; data: SimulationRunState }
  | { event: 'post_created'; data: PostCreatedEvent }
  | { event: 'control'; data: ControlPayload }

// Parse-Function
function parseFrame(raw: { event: string; data: string }): StreamEventFrame | null {
  switch (raw.event) {
    case 'post_created': {
      const parsed = PostCreatedEventSchema.safeParse(JSON.parse(raw.data))
      if (!parsed.success) {
        console.warn('post_created frame failed Zod parse', parsed.error)
        return null
      }
      return { event: 'post_created', data: parsed.data }
    }
    // ... existing cases
  }
}
```

- [ ] **Step 6.4: Tests grün + Commit**

---

## Task 7: Worklog + Verification-Gate

**Files:**
- Create: `docs/2026-05-15-fe-redesign-slice-5-pre-worklog.md`

- [ ] **Step 7.1: Worklog mit Pflicht-Sektionen**

- Was Pipeline jetzt kann: PostCreatedEvent geht von OASIS-Action → Redis → SSE → Frontend-Zod-Schema durch.
- Test-Delta (Backend + Frontend).
- Schema-Drift-Check (`git diff --exit-code schemas/`).
- Skip-Begründungen (Tool-Pflicht).
- Offene Punkte: bspw. wenn voice_register noch nicht für alle Personas gesetzt ist → Followup.

- [ ] **Step 7.2: Backend + Frontend Verification-Gate**

```bash
# Backend
cd /private/tmp/agora-fe-redesign-5-pre/backend
uv run pytest -x -q
uv run ruff check app && uv run mypy app

# Schema-Drift-Gate
cd ..
git diff --exit-code schemas/

# Frontend
cd frontend
bun run typecheck && bun run test:coverage && bun run build && bun run lint
```

Alle exit 0. Schema-Drift = exit 0 (kein Diff, weil dump_schemas in Task 2 committed wurde).

- [ ] **Step 7.3: code-review-graph update**

```bash
cd /private/tmp/agora-fe-redesign-5-pre
code-review-graph update
```

- [ ] **Step 7.4: Rückmeldungs-Format**

```
Branch: feat/fe-redesign-5-pre-post-event
Letzter Commit: <hash>
Test-Delta: Backend +<N> (contracts +7, services +3, api +1). Frontend +<M> (contracts +2)
Schema-Drift: clean
SSE-Smoke (lokal): post_created-Frame in stub-Mode reproduzierbar / failed
Gaps: <konkrete Followups, z.B. Mastodon-Plattform out-of-scope>
Worklog: docs/2026-05-15-fe-redesign-slice-5-pre-worklog.md
```

---

## Self-Review

**Spec coverage:**
- ✅ PostCreatedEvent als Layer-0-Contract → Task 1+2
- ✅ Enum-Werte für platform/voice_register → Task 2
- ✅ event_bus emit_post_created → Task 3
- ✅ SSE-Frame `event: post_created` → Task 4
- ✅ OASIS-Runner emittiert nach CREATE_POST → Task 5 (mit Bridge-Disclaimer)
- ✅ Zod-Spiegel mit Schema-Drift-Gate → Task 6
- ⚠️ Mastodon/Threads als zukünftige Plattformen — bewusst out-of-scope (ADR-Hint im Code-Kommentar, Enum-Erweiterung wäre eigener Slice mit Migration der bestehenden SQLite-Daten)
- ⚠️ `voice_register` muss in der DB-Persona-Tabelle bereits gepflegt sein — falls Lücken: Worker findet bei Smoke-Test heraus, escaliert als Folge-Slice.

**Placeholder scan:** alle Code-Blöcke konkret, außer Task 3.2 + 4.1 sind als Skelett markiert weil sie auf existing-Test-Pattern aufbauen, die der Worker im Worktree liest.

**Type consistency:** `Platform`/`PlatformSchema`, `VoiceRegister`/`VoiceRegisterSchema`, `PostCreatedEvent`/`PostCreatedEventSchema`, Enum-Werte (`reddit`/`twitter`/`formal`/`casual`/`jugendsprache`) durchgehend gleich zwischen Pydantic und Zod.

**Cross-Slice-Konsistenz:** Slice 5 (Frontend Sim-Feed) konsumiert `useEventStream` mit der neuen Type-Variante. Plan-Slot dort: `frame.event === 'post_created'` → in die richtige Column einsortieren (`platform`), threading via `parent_post_id`.

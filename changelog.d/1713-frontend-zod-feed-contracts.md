### Frontend (#1713)

- `PostCreatedEventSchema` (v2): `PostKind`-Enum, `like_count`, `parent_comment_id`, `parent_persona_id`, `parent_persona_name`, `quote_body`, `quoted_post_id`, `reposted_post_id`, `root_post_id`, `round_num` — alle nullable+optional, rückwärtskompatibel. Drift-Gate-Test deckt alle Backend-Properties ab.
- Neu `frontend/src/contracts/simActionContract.ts`: `SimActionTypeSchema`, `SimActionRecordSchema`, `SimActionPageSchema`, `RoundSummarySchema`, `RoundsResponseSchema` — strikt, mit Drift-Gate- und Sample-Payload-Tests.
- `getSimulationActions` → `Promise<ApiEnvelope<SimActionPage>>`, Params `cursor`/`action_type` statt `offset`; neu `getSimulationRounds(simulationId)` → `Promise<ApiEnvelope<RoundsResponse>>`.

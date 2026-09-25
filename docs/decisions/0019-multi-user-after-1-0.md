# ADR-0019: Multi-User erst nach 1.0

- Status: Accepted (Owner-Entscheidung 2026-09-25)
- Datum: 2026-09-25
- Löst ab: den Zeitpunkt aus [ADR-0018](0018-multi-user-before-1-0.md). Dessen
  technische Entscheidungen (Principal, Auth-Modi, Workspaces, RLS, Realtime)
  bleiben das Zielbild für die Zeit nach 1.0.
- Stellt wieder her: ROADMAP-Regel 4 („Kein Multi-User-/SaaS-/Kubernetes-Ausbau
  vor einem belastbaren Single-User-1.0“) und das Single-User-Zielbild aus
  [ADR-0001](0001-auth-model.md) für v1.0.
- Bezug: Epic [#1610](https://github.com/arn0ld87/agora/issues/1610),
  [`docs/plans/supabase.md`](../plans/supabase.md)

## Kontext

ADR-0018 hat am 2026-09-25 Workspaces, Supabase Auth, JWT, RLS, den
Frontend-Auth-Client und Realtime vor 1.0 gezogen. Am selben Tag gemergt sind
M1 bis M8 aus Epic #1610 (#1619, #1621, #1623, #1624, #1625, #1626, #1628).
Offen ist der Nachzügler-PR #1627 zum Frontend-Auth-Client.

Der Owner hat die Reihenfolge am selben Tag zurückgenommen: 1.0 bleibt
Single-User. Multi-User folgt erst danach.

## Entscheidung

1. **1.0 ist Single-User.** Auth-Wahrheit für 1.0 sind Master-Token
   (`AGORA_AUTH_TOKEN`), Workspace-API-Keys (`ago_…`) und signierte Tickets.
   Die Freigabekriterien in `ROADMAP.md` gelten für diesen Umfang.
2. **Der gemergte Multi-User-Code bleibt im Repository und ist inaktiv.**
   - `AGORA_AUTH_BACKEND` steht im Default auf `hybrid`. Ohne
     `AGORA_SUPABASE_JWT_ISSUER` verhält sich das wie `legacy`.
   - Ohne JWT gibt es keine Anmeldung und keine Workspace-Wahl. Die Daten
     liegen im Default-Workspace, und das Frontend bleibt im Legacy-Modus.
   - `AGORA_SUPABASE_REALTIME` steht im Default auf aus.
   - Die Alembic-Migrationen (Workspaces, `workspace_id`, RLS, Publication)
     sind gemergt und laufen mit. Ohne Tenant-Modus wirken sie über den
     Default-Workspace und den Systemkontext.
3. **Kein weiterer Ausbau vor 1.0.**
   - Neue Arbeit unter Epic #1610 ruht.
   - Fehlerbehebungen am gemergten Code sind erlaubt, wenn sie Legacy-
     oder Single-User-Betrieb betreffen oder eine Sicherheitslücke schließen.
4. **Nicht einschalten vor 1.0.** Der Produktivbetrieb setzt weder
   `AGORA_SUPABASE_JWT_ISSUER` noch `AGORA_SUPABASE_REALTIME`, und GoTrue
   bleibt ohne offene Registrierung (`DISABLE_SIGNUP=true`).

## Konsequenzen

- ROADMAP, Release-Priorität, STATUS und Supabase-Plan führen Multi-User
  wieder unter „nicht vor 1.0“.
- Der Metadaten-Cutover auf PostgreSQL (#1592) ist davon unabhängig und
  bleibt Teil von 1.0.
- Nach 1.0 setzt Epic #1610 auf dem gemergten Stand auf; ADR-0018 beschreibt
  das Zielbild.

## Nicht entschieden

- Ob der Default von `AGORA_AUTH_BACKEND` vor 1.0 auf `legacy` zurückgeht.
  Heute verhält sich `hybrid` ohne Issuer wie `legacy`, der Startlog sagt das.
- Ob #1627 vor 1.0 gemergt oder bis nach 1.0 geparkt wird.

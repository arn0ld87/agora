# Sub-Slice 40 — Claude-Review erlaubt Dependabot-PRs

**Datum:** 2026-05-03
**Layer:** — (CI / `.github/workflows/`)
**Vorgänger:** PR #188 (Claude-Workflows hinzugefügt), Sub-Slice 39 (Dependabot aktiviert)

## Was

`.github/workflows/claude-code-review.yml`:

- Parameter `allowed_bots: 'dependabot'` an die `anthropics/claude-code-action@v1`
  übergeben.

## Warum

Direkt nach dem Dependabot-Aktivieren (Sub-Slice 39) feuerten 10 Bump-PRs.
Alle 10 hatten `claude-review = FAILURE` mit der Action-Meldung:

```
Workflow initiated by non-human actor: dependabot (type: Bot).
Add bot to allowed_bots list or use '*' to allow all bots.
```

Default-Verhalten der Action blockt Bot-PRs aus Schutz vor Workflow-Injection
und Token-Verbrauch. Da Agora aktuell keine externen Bots außer
Dependabot orchestriert, ist explicit-allow präziser als `'*'`:

- `'dependabot'` — review läuft, Budget bleibt überschaubar
- `'*'` — würde auch Copilot, google-labs-jules, claude[bot] mit-reviewen,
  was bei 10–20 PRs/Woche ungeplant Tokens kostet.

## Verifikation

- YAML-Lint ok (per `uv run python -c "yaml.safe_load(...)"`)
- Echtprüfung erst sichtbar, sobald entweder
  - eine neue Dependabot-PR erscheint, ODER
  - eine bestehende PR via `gh run rerun` nochmal getriggert wird.

## Out of Scope

- Re-Run der bereits roten claude-review-Jobs auf #189–#198 — separater Schritt
  per `gh run rerun`, falls Reviews nachträglich gewünscht.
- ANTHROPIC_API_KEY / OAUTH-Token-Setup: schon korrekt eingerichtet
  (Sekret `CLAUDE_CODE_OAUTH_TOKEN` wird bereits aufgelöst — Action kommt
  bis zum Bot-Check).

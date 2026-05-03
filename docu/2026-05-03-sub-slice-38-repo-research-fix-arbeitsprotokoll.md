# Sub-Slice 38 — `/repo-research` Slash-Command-Bugfix

**Datum:** 2026-05-03
**Layer:** — (Tooling, `.claude/commands/`)
**Vorgänger:** /repo-research wurde in dieser Session neu hinzugefügt (kein eigener Slice — Tooling-Komfort)

## Was

`.claude/commands/repo-research.md`:

- `openIssuesCount` aus dem `gh repo view --json`-Field-Set entfernt — gibt's
  in der gh-CLI-GraphQL-Layer schlicht nicht (verfügbare Felder enthalten nur
  `issues` als Connection, nicht `openIssuesCount`).
- Stattdessen zweiter Call: `gh api repos/$ARGUMENTS --jq '{open_issues, has_issues, has_wiki, has_projects, archived, network_count, subscribers_count}'`.
- Zusätzlich `repositoryTopics` und `visibility` ins GraphQL-Set aufgenommen
  (waren beim ersten Smoke-Run nützliche Zusatz-Felder).

## Warum

Beim ersten Echtlauf gegen `arn0ld87/agora` brach Step 1 mit
`Unknown JSON field: "openIssuesCount"` ab und kaskadierte alle parallelen
Folgesteps weg. Bug war im Command-Template, nicht im Repo unter Test.

## Verifikation

```bash
gh repo view arn0ld87/agora --json \
  name,description,owner,homepageUrl,licenseInfo,stargazerCount,forkCount,\
watchers,pushedAt,createdAt,updatedAt,isArchived,isFork,isTemplate,\
languages,primaryLanguage,defaultBranchRef,diskUsage,repositoryTopics,visibility \
  | jq .name
# → "agora"  (exit 0)

gh api repos/arn0ld87/agora --jq '.open_issues'
# → 17       (exit 0)
```

Kompletter Smoke-Run von `/repo-research arn0ld87/agora` erzeugt jetzt
saubere Stammdaten + REST-Health-Flags ohne Crash.

## Out of Scope

- Generische Coverage für andere Repos (nur Agora als Smoke).
- README-Step (Step 6) bleibt von einer Permission-Frage abhängig
  (`xargs curl -sSL`) — bewusst nicht workaroundet, weil User-Permission-UI
  das beim ersten Aufruf abfragt und freigibt.

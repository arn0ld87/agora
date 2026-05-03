---
description: Schnell-Recherche eines GitHub-Repos via gh CLI — Metadaten, Aktivität, Dependencies, Issues.
argument-hint: <owner/repo>
allowed-tools: Bash, WebFetch
---

# /repo-research $ARGUMENTS

Strukturierte Erst-Sichtung eines fremden GitHub-Repos. Zweck: Make-or-Buy /
Tech-Eval / Vendor-Risk in 2 Minuten. Kein Code-Klonen, nur Lesen.

Wenn `$ARGUMENTS` leer ist: stoppe und frage nach `<owner/repo>`.

## 1. Stammdaten + Aktivität

```bash
# GraphQL-Felder über gh repo view --json
gh repo view $ARGUMENTS --json \
  name,description,owner,homepageUrl,licenseInfo,stargazerCount,forkCount,\
watchers,pushedAt,createdAt,updatedAt,isArchived,isFork,isTemplate,\
languages,primaryLanguage,defaultBranchRef,diskUsage,repositoryTopics,visibility \
  | jq

# Open-Issues + Health-Flags via REST (kein gleichwertiges GraphQL-Feld)
gh api repos/$ARGUMENTS --jq \
  '{open_issues, has_issues, has_wiki, has_projects, archived, network_count, subscribers_count}'
```

## 2. Release- und Commit-Frequenz

```bash
gh api repos/$ARGUMENTS/releases --jq \
  '[.[] | {tag: .tag_name, published: .published_at, prerelease}] | .[0:5]'

gh api "repos/$ARGUMENTS/commits?per_page=10" --jq \
  '[.[] | {sha: .sha[0:8], date: .commit.author.date, msg: (.commit.message | split("\n")[0])}]'
```

## 3. Maintainer-Footprint

```bash
gh api "repos/$ARGUMENTS/contributors?per_page=10" --jq \
  '[.[] | {login, contributions}]'
```

## 4. Issue- und PR-Health

```bash
gh api "repos/$ARGUMENTS/issues?state=open&per_page=1" --jq 'length'
gh issue list  --repo $ARGUMENTS --limit 5  --json number,title,createdAt,labels
gh pr    list  --repo $ARGUMENTS --limit 5  --json number,title,createdAt,isDraft,reviewDecision
```

## 5. Security & Dependencies

```bash
# Existiert eine SECURITY.md / Dependabot / Snyk?
gh api "repos/$ARGUMENTS/contents/SECURITY.md" --jq '.path' 2>/dev/null || echo "kein SECURITY.md"
gh api "repos/$ARGUMENTS/contents/.github/dependabot.yml" --jq '.path' 2>/dev/null || echo "kein dependabot.yml"

# Falls Python: pyproject / requirements lesen
gh api "repos/$ARGUMENTS/contents/pyproject.toml" --jq '.download_url' 2>/dev/null \
  | xargs -r curl -sSL | head -80
```

## 6. README-Top

```bash
gh api "repos/$ARGUMENTS/readme" --jq '.download_url' \
  | xargs curl -sSL | head -120
```

## 7. Report (Markdown, knapp)

Fasse zusammen — Format:

```
## $ARGUMENTS — Snapshot ($(date +%Y-%m-%d))

- **Was:** <1 Satz Beschreibung>
- **Lizenz:** <SPDX> — <DACH-Kompatibilität, falls relevant>
- **Aktivität:** <last commit> · <release-frequenz> · <stars/forks>
- **Bus-Faktor:** <Top-3 Contributors mit Anteil>
- **Health:** <open issues> · <stale-Indikator>
- **Security:** <SECURITY.md y/n> · <dependabot y/n> · <bekannte CVE-Hits, falls geprüft>
- **Stack:** <Sprachen + Hauptdeps>
- **Risiken:** <US-Cloud-Lock-in? · API-Stabilität? · Maintainer-Konzentration?>
- **Empfehlung:** <Use / Watch / Skip> + 1-Satz-Begründung
```

Keine Tool-Output-Dumps in den Report — nur die destillierten Fakten.
Wenn eine Sektion leer ist, kurz erwähnen ("keine Releases vorhanden")
statt weglassen.

---
description: MAI-13 — Dependabot PRs #323 (mistune) und #326 (pygments) cleanup via uv lock --upgrade-package.
allowed-tools: Read, Bash, Grep, Glob, Edit, Write
---

# /fix-mai-13-dependabot-cleanup — Mistune + Pygments cleanup

## Ziel

`mistune` und `pygments` sind auf der jeweils neuesten Patch-Version im `uv.lock`. Dependabot-PRs #323 und #326 sind merged oder durch direkten Lockfile-Bump obsolet geschlossen. `pip-audit` läuft grün.

## Voraussetzungen

- Worktree: `/Volumes/T7/Projekte/agora-worktrees/mai-13/`.
- Branch: `chore/mai-13-deps-mistune-pygments`.

## Schritt-für-Schritt

### Schritt 1: Status der Dependabot-PRs

```bash
cd /Volumes/T7/Projekte/agora-worktrees/mai-13
gh pr view 323 --json state,title,headRefName,mergeable,statusCheckRollup
gh pr view 326 --json state,title,headRefName,mergeable,statusCheckRollup
```

### Schritt 2: Current-Versionen lesen

```bash
cd backend
grep -E "^name = \"(mistune|pygments)\"" -A 1 uv.lock | head -20
uv pip list 2>/dev/null | grep -iE "mistune|pygments" || true
```

### Schritt 3: Lockfile-Bump

```bash
cd /Volumes/T7/Projekte/agora-worktrees/mai-13/backend

# Punkt-genau auf neueste Patch-Version
uv lock --upgrade-package mistune --upgrade-package pygments

# Diff sichten — nur die zwei Packages dürfen sich ändern
git diff uv.lock | head -50
```

### Schritt 4: Re-Sync + Smoke

```bash
cd /Volumes/T7/Projekte/agora-worktrees/mai-13/backend

# Sync gegen aktualisiertes Lockfile
uv sync --frozen

# Import-Smokes — beide Libs werden von mehreren Pfaden genutzt
uv run python -c "
import mistune
import pygments
from pygments.lexers import get_lexer_by_name
from pygments.formatters import HtmlFormatter
print(f'mistune {mistune.__version__}')
print(f'pygments {pygments.__version__}')

# Smoke: rendere Markdown mit Code-Block
md = mistune.create_markdown()
out = md('```python\nx = 1\n```')
assert '<pre>' in out, 'mistune-render fehlerhaft'

# Smoke: Pygments-Lexer
lexer = get_lexer_by_name('python')
formatter = HtmlFormatter()
print('OK MAI-13')
"
```

### Schritt 5: pip-audit

```bash
cd /Volumes/T7/Projekte/agora-worktrees/mai-13/backend
uv run pip-audit --skip-editable -l 2>&1 | tee /tmp/mai-13-audit.txt
# Sollte keine HIGH/CRITICAL CVE listen
```

### Schritt 6: Volltest

```bash
cd /Volumes/T7/Projekte/agora-worktrees/mai-13/backend
uv run pytest -x -q
```

### Schritt 7: Dependabot-PRs schließen

```bash
# Nach Push auf main: PRs zumachen mit Verweis
gh pr close 323 --comment "Closed by MAI-13 — Lockfile-Bump direkt in chore/mai-13-deps-mistune-pygments."
gh pr close 326 --comment "Closed by MAI-13 — Lockfile-Bump direkt in chore/mai-13-deps-mistune-pygments."
```

## Verifikation

```bash
# 1) Lockfile-Diff nur 2 Packages
git diff --stat uv.lock
# Erwartet: 1 file changed, <kleine Zahl>

# 2) Import-Smoke (siehe Schritt 4)

# 3) pip-audit clean
uv run pip-audit --skip-editable -l | grep -E "HIGH|CRITICAL" && exit 1 || echo "OK"

# 4) Voll-Test
cd backend && uv run pytest -x -q

# 5) PRs geschlossen
gh pr view 323 --json state --jq '.state'
gh pr view 326 --json state --jq '.state'
# Erwartet: CLOSED
```

## Warum?

Beide PRs sind reine Patch-Bumps ohne API-Bruch. Sie hängen seit ~7 Tagen offen, weil das Lockfile-Sync händisch gemacht werden muss. Direkter `uv lock --upgrade-package`-Push ist schneller und vermeidet Dependabot-Merge-Konflikte mit `camel-oasis==0.2.5`-Pin (PR #315).

## Nächste Schritte

1. Worklog `docs/2026-05-14-mai-13-arbeitsprotokoll.md` mit pip-audit-Output.
2. CHANGELOG: `MAI-13 · mistune + pygments Lockfile-Bump (Dependabot #323 + #326 closed).`
3. `/agora-mai-next-task` → Block A abgeschlossen, weiter mit Block B (`/fix-mai-02-evidence-routing`).

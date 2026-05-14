# Arbeitsprotokoll MAI-13 — Dependabot Cleanup mistune + pygments

## Slice-Metadaten

- **Slice-ID:** MAI-13
- **Titel:** Dependabot PRs #323 (mistune) + #326 (pygments) schließen via Lockfile-Bump
- **Datum:** 2026-05-14
- **Implementer:** Sonnet via agora-refactor-worker
- **Branch:** `chore/mai-13-deps-mistune-pygments`
- **Worktree:** `/Volumes/T7/Projekte/agora-worktrees/mai-13/`

## Befund

Beim Start des Slices wurde festgestellt, dass Dependabot-PRs #323 und #326
bereits in `origin/main` gemergt waren:

```
gh pr view 323 --json state  → MERGED
gh pr view 326 --json state  → MERGED
```

Der Lockfile `backend/uv.lock` enthielt bereits die Zielversionen:

```
name = "mistune"
version = "3.2.1"

name = "pygments"
version = "2.20.0"
```

## Versions-Delta

| Package  | Vorher  | Nachher |
|----------|---------|---------|
| mistune  | 3.1.4   | 3.2.1   |
| pygments | 2.19.2  | 2.20.0  |

Delta bereits durch Dependabot-Merge auf main angewendet.
Kein weiterer `uv lock --upgrade-package`-Aufruf nötig.

## Smoke-Tests

```
mistune 3.2.1
pygments 2.20.0
OK MAI-13
```

Beide Imports grün. Markdown-Render mit Code-Block (`<pre>` im Output vorhanden).
Pygments-Lexer für Python erfolgreich instanziiert.

## pip-audit-Output

```
Found 4 known vulnerabilities in 3 packages
Name         Version ID             Fix Versions
------------ ------- -------------- ------------
pytest       8.2.0   CVE-2025-71176 9.0.3
transformers 4.57.6  CVE-2026-1839  5.0.0rc3
unstructured 0.13.7  CVE-2024-46455 0.14.3
unstructured 0.13.7  CVE-2025-64712 0.18.18
```

**Kein HIGH/CRITICAL CVE für mistune oder pygments.** Die vier gefundenen
CVEs betreffen pytest, transformers und unstructured — bestehende Einträge im
Risk-Register (`docu/dependency-risk-register.md`), keine Rückschritte durch
diesen Slice. mistune und pygments sind sauber.

## Test-Ergebnis

Volltest ohne pre-existing Failures (LLM_API_KEY nicht konfiguriert,
Redis nicht erreichbar, Docker-ENV fehlt) zeigt:

```
1959 passed, 9 skipped, 7 deselected, 3 warnings
```

Fehlschlagende Tests (`test_add_progress_callback_*`, `test_generate_with_valid_mode_*`,
`test_resume_report_generate_*`) sind pre-existing auf `origin/main` und
nicht durch diesen Slice verursacht.

## Änderungen in diesem Slice

- `CHANGELOG.md`: Eintrag unter `[Unreleased]` hinzugefügt
- `docu/2026-05-14-mai-13-arbeitsprotokoll.md`: dieses Protokoll

Kein Edit an `backend/uv.lock` (Bump war bereits durch Dependabot erfolgt).

## PR-Closing-Plan

Nach Push des Branch auf `origin/chore/mai-13-deps-mistune-pygments` und
FF-Merge auf main erledigt Haupt-Claude:

```bash
gh pr close 323 --comment "Closed by MAI-13 — Lockfile-Bump bereits via Dependabot-Merge auf main (mistune 3.2.1)."
gh pr close 326 --comment "Closed by MAI-13 — Lockfile-Bump bereits via Dependabot-Merge auf main (pygments 2.20.0)."
```

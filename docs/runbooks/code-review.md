# Code-Review und PR-Workflow

Dieses Runbook beschreibt Review-Pflichten für Agora.

## Review-Haltung

Priorität haben:

1. Korrektheit und Datenfluss.
2. Security und Secret-Schutz.
3. Vertrags-/Schema-Kompatibilität.
4. Tests und CI-Gates.
5. Wartbarkeit und Lesbarkeit.

Style-Fragen sind sekundär, außer sie verbergen echte Risiken.

## Vor dem PR

```bash
npm run check
git diff --check
```

Bei Contract-Änderungen zusätzlich:

```bash
cd backend && uv run python -m app.contracts.dump_schemas
git diff --exit-code schemas/
```

Bei Deployment-/Security-Änderungen passende Smoke-Checks und Doku aktualisieren.

## Nach `gh pr create`

```bash
sleep 90
gh api repos/arn0ld87/agora/pulls/<NR>/reviews  --jq '.[] | {author, body, state}'
gh api repos/arn0ld87/agora/pulls/<NR>/comments --jq '.[] | {path, line, body}'
```

Gemini-Code-Assist-Findings:

- **HIGH:** immer adressieren, bevor gemerged wird.
- **MEDIUM:** je nach Scope fixen oder begründet ablehnen.
- **LOW:** kann out of scope bleiben, wenn das im Arbeitsprotokoll oder PR-Kommentar steht.

## Merge

Erst nach Review-Sichtung:

```bash
git checkout main
git merge --ff-only <branch>
git push origin main
```

Kein `gh pr merge --auto` ohne Findings-Sichtung. Kein `git push --no-verify` ohne explizite Freigabe.

## Security-Checkliste

- Keine Secrets in Diffs.
- Keine neuen `?token=`-URLs.
- Keine CORS-/Auth-Abschwächung.
- Keine CVE-Ignores ohne Issue, Owner, Deadline und Hardstop.
- Keine produktiven `print()`-Statements; strukturiertes Logging nutzen.
- Rate-Limits, AuthZ, Input-Validation und Logging ohne PII prüfen, wenn API/Infra betroffen ist.

## Dokumentations-Checkliste

- README bleibt Einstieg, keine Roadmap-Ablage.
- Dauerhafte Details unter `docs/`.
- Statuszahlen nur in `docs/status.md`.
- Historische Worklogs unter `docs/archive/worklogs/`.
- Links nach Moves aktualisieren.

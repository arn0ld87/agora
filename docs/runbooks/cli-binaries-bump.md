# CLI-Provider-Binaries anheben

**Stand:** 2026-10-11 (#1861)

Das Image bringt zwei CLI-Binaries mit, die Agora als Provider anspricht: `claude` (`claude_cli`) und `codex` (`codex_cli`). Beide sind im `Dockerfile` mit Version und je einem SHA256-Wert für amd64 und arm64 gepinnt. Dependabot erfasst solche `ARG`-Downloads nicht. Den Bump übernimmt `.github/workflows/cli-binaries-bump.yml`.

## Ablauf

Der Workflow läuft montags 05:20 UTC und auf manuellen Start.

1. `backend/scripts/bump_cli_binaries.py` ermittelt die Zielversion.

   | Binary | Quelle der Version | Quelle der Hashes |
   |---|---|---|
   | `claude` | Kanal `stable` (`downloads.claude.ai/claude-code-releases/stable`) | `manifest.json` der Version |
   | `codex` | neuestes Nicht-Prerelease von `openai/codex` | Feld `digest` der Release-Assets |

2. Das Skript lädt beide Dateien und vergleicht ihren SHA256 mit der Herstellerangabe. Der PR-Build baut nur amd64; der arm64-Hash würde sonst erst beim Publish auf `main` geprüft.
3. Es ersetzt die drei `ARG`-Zeilen und schreibt `changelog.d/1861-bump-<binary>-cli.md`.
4. Der Workflow öffnet je Binary einen eigenen PR vom Branch `build/bump-<binary>-cli`. Ein noch offener Bump-PR wird fortgeschrieben.

Ist der Pin aktuell, endet der Lauf ohne PR.

## Was den PR prüft

`build-only` in `docker-image.yml` baut das Image. Die Stages `claude-cli` und `codex-cli` brechen ab, wenn

- der Hash nicht passt,
- `--version` scheitert,
- ein Flag aus `CLAUDE_CODE_REQUIRED_FLAGS` bzw. `CODEX_REQUIRED_EXEC_FLAGS` in der CLI-Hilfe fehlt,
- `codex debug models` fehlt.

`backend/tests/scripts/test_bump_cli_binaries.py` gleicht beide Flag-Listen mit der Kommandozeile ab, die die Provider tatsächlich bauen. Wer in `build_claude_cli_command()` oder `build_codex_cli_command()` ein Flag ergänzt, muss es im `Dockerfile` nachtragen.

**Nicht geprüft** wird die Ausgabeform der CLI, etwa das JSON von `claude -p --output-format json`. Ein Release, das sie ändert, besteht den Build. Vor dem Merge eines Bumps über mehrere Minor-Versionen die Release-Notes lesen.

Der Workflow merged nicht selbst.

## Manuell starten

```bash
gh workflow run cli-binaries-bump.yml -f tool=beide
```

Eine feste Version braucht ein einzelnes Binary:

```bash
gh workflow run cli-binaries-bump.yml -f tool=claude -f version=2.1.287
```

Lokal, ohne PR:

```bash
cd backend && uv run python scripts/bump_cli_binaries.py --tool claude
```

## Einmalige Einrichtung

Der Workflow braucht das Actions-Secret `BUMP_BOT_TOKEN` mit einem Token von `arn0ld87-bot`. Ein PR, den das Standard-`GITHUB_TOKEN` öffnet, startet keine weiteren Workflows; die Pflicht-Checks blieben auf „Expected".

`build-only` läuft seit #1861 auf jedem PR, damit der Check als Pflicht-Check in den Branch-Schutz von `main` aufgenommen werden kann.

## Fehlerbilder

| Symptom | Ursache | Abhilfe |
|---|---|---|
| Lauf rot bei „Eingaben prüfen" | Secret fehlt oder Version mit `tool=beide` | Secret setzen bzw. einzelnes Binary wählen |
| `Hash-Abweichung für …` | Herstellerangabe und Datei passen nicht zusammen | Nicht von Hand übersteuern; später erneut starten, bei Wiederholung beim Hersteller nachsehen |
| `unerwartetes Versionsformat` | Kanal-Endpunkt liefert etwas anderes als `X.Y.Z` bzw. `rust-vX.Y.Z` | Endpunkt prüfen, Skript anpassen |
| Bump-PR rot in `build-only` mit `Flag … fehlt in --help` | Die neue CLI kennt ein Provider-Flag nicht mehr | Provider anpassen, erst dann bumpen |
| Checks am Bump-PR starten nicht | Token abgelaufen oder ohne Push-Recht | Token erneuern, Secret neu setzen |

Fehlschläge meldet nur GitHubs Standard-Mail für gescheiterte Workflow-Läufe.

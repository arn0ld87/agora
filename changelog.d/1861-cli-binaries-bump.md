### Added

- **Die gepinnten CLI-Provider-Binaries bleiben per Workflow aktuell (#1861, 11.10.2026).** `Dockerfile` pinnt `claude` und `codex` mit Version und zwei SHA256-Werten; Dependabot erfasst diese `ARG`-Downloads nicht, die Pins alterten still. `.github/workflows/cli-binaries-bump.yml` ermittelt montags die Zielversion (Claude Code: Kanal `stable`, Codex: neuestes Nicht-Prerelease), `backend/scripts/bump_cli_binaries.py` liest die Hashes aus der Herstellerquelle, prüft sie für amd64 und arm64 gegen die ausgelieferten Dateien und öffnet je Binary einen eigenen Pull Request unter `arn0ld87-bot`. Der Workflow merged nicht selbst. Runbook: `docs/runbooks/cli-binaries-bump.md`.

### Changed

- **Der Image-Build prüft die von den Providern benutzten CLI-Flags (#1861).** Bisher endeten die Stages `claude-cli` und `codex-cli` mit `--version`; das belegt nur, dass das Binary startet. Jetzt bricht der Build ab, wenn `claude --help` bzw. `codex exec --help` eines der Flags nicht kennt, die `build_claude_cli_command()` und `build_codex_cli_command()` übergeben, oder wenn `codex debug models` fehlt. Ein Test gleicht die Listen im `Dockerfile` mit den Providern ab. Die Ausgabeform der CLI bleibt ungeprüft.
- **`build-only` läuft auf jedem Pull Request (#1861).** Der Pfadfilter in `docker-image.yml` ist entfernt, damit der Check Pflicht-Check werden kann, ohne PRs außerhalb des Filters zu sperren. Wegen `**/*.md` griff der Filter schon vorher bei fast jedem PR.

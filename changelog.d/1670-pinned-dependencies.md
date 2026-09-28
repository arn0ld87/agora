### Security

- CI-Workflows (`ci.yml`, `contract-gates.yml`, `version-drift.yml`) installieren `uv` über die per Commit-SHA gepinnte Action `astral-sh/setup-uv` statt über ein ungepinntes `pip install uv`. Die `claude-cli`-Stage im `Dockerfile` bezieht das Claude-Code-Binary direkt von `downloads.claude.ai` und prüft es gegen einen gepinnten SHA256 je Architektur, statt `install.sh` ungeprüft auszuführen. Behebt die Scorecard-Alerts `PinnedDependencies`. (#1670)

### Fixed

- CI: `prod-proxy-smoke` blockte via Harden-Runner-Egress jeden Zugriff auf `ghcr.io` und scheiterte damit auf jedem Release-/Tag-Push am Pull des `astral-sh/uv`-Basis-Images — der GHCR-Publish wurde dadurch nie erreicht. `ghcr.io:443` und `pkg-containers.githubusercontent.com:443` in die Smoke-Allowlist aufgenommen ([#1145](https://github.com/arn0ld87/agora/pull/1145)).

### Security

- Supply-Chain-Cooldown: neue Paket-Releases werden erst sieben Tage nach
  Veröffentlichung übernommen. `backend/pyproject.toml` setzt dafür
  `exclude-newer = "7 days"` (uv), `frontend/bunfig.toml` setzt
  `minimumReleaseAge` (bun) und `.github/dependabot.yml` einen `cooldown` von
  sieben Tagen für alle vier Ökosysteme. Dependabot-Security-Updates sind vom
  Cooldown ausgenommen. Zwei Pakete, die zum Zeitpunkt der Umstellung jünger
  als sieben Tage waren, bleiben über `exclude-newer-package` freigegeben
  (`virtualenv` 21.14.2 als CVE-Fix, `oauthlib` 4.0.0); ohne die Freigabe hätte
  uv beide zurückgestuft.

### Fixed

- CI: `releases.astral.sh:443` steht jetzt in der Harden-Runner-Allowlist der
  vier `ci.yml`-Jobs, die uv einrichten. Der Endpunkt wurde im Block-Modus
  abgewiesen (Lauf 37155231295).

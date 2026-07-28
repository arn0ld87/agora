# Self-hosted Runner `meinserver-arm64`

Ein GitHub-Actions-Self-hosted-Runner läuft als systemd-Dienst auf `armserver`
(Tailscale, arm64) und ist im Repo `arn0ld87/agora` registriert.

## Sicherheitskontext (public Repo)

`agora` ist ein **public** Repository. Self-hosted Runner auf public Repos sind
laut GitHub ein bekanntes Risiko: Fork-PRs können Code ausführen, der dann auf
dem eigenen Host läuft. `meinserver`/`armserver` betreibt daneben produktiven
Agora-Traffic (Compose-Stack hinter Traefik, Neo4j, Ollama) — ein kompromittierter
CI-Job hätte Netzwerkzugriff auf diese Dienste.

Gegenmaßnahmen:

1. **Repository-Settings → Actions → General → "Fork pull request workflows
   from outside collaborators"** ist auf **"Require approval for all outside
   collaborators"** gesetzt (nicht über die REST-API erreichbar, nur UI).
2. Kein Workflow-Job darf `runs-on: [self-hosted, ...]` für den
   `pull_request`-Trigger verwenden — nur für `push` (main/release/rc/tags)
   und `workflow_dispatch`. Siehe `.github/workflows/docker-image.yml`,
   Job `build-only`: `runs-on` wählt `ubuntu-latest` für `pull_request` und
   den self-hosted Runner nur für die übrigen Trigger.
3. `step-security/harden-runner` läuft nur auf `ubuntu-latest`
   (`if: github.event_name == 'pull_request'`) — auf dem self-hosted Runner
   würde der Step maschinenweite Egress-iptables-Regeln setzen und damit
   den produktiven Traffic auf `meinserver` während des CI-Laufs einschränken.

**Bekannte, noch offene Lücke:** Der Event-Filter (`pull_request` vs. `push`/
`workflow_dispatch`) steuert nur, *welche* Jobs den Runner erreichen — er
schafft keine echte Laufzeit-Isolation. Der Runner läuft persistent als
systemd-Dienst, nicht ephemer und nicht containerisiert. Jeder Job, der ihn
erreicht (auch ein legitimer `push` auf `main`), hat vollen Zugriff auf den
Host und auf Zustand, den vorherige Jobs hinterlassen haben. **Mandatory
Security-Requirement für dieses Setup:** Bevor der Runner für sicherheits-
kritische oder von mehreren Personen auslösbare Workflows genutzt wird, muss
er entweder (a) mit `--ephemeral` (Neu-Registrierung nach jedem Job) oder
(b) containerisiert/als Wegwerf-VM pro Job betrieben werden. Bis dahin gilt
der aktuelle Event-Filter als Mindestschutz, nicht als vollständige Isolation.
Tracking: siehe „Erweiterung auf weitere Jobs" unten — kein Job darf ergänzt
werden, ohne diese Lücke erneut zu bewerten.

## Runner-Details

- Name: `meinserver-arm64`
- Labels: `self-hosted`, `Linux`, `ARM64`, `meinserver`
- Host: `armserver` (SSH-Alias), Pfad `~/actions-runner`
- Betrieb: systemd-Dienst `actions.runner.arn0ld87-agora.meinserver-arm64.service`
- Zweck: native arm64-Docker-Builds ohne QEMU-Emulation; potenziell künftig
  Tests gegen bereits laufende interne Dienste (Neo4j/Ollama auf meinserver)

## Erweiterung auf weitere Jobs

Bevor ein weiterer Job auf diesen Runner umgestellt wird: prüfen, ob er auf
`pull_request` von Forks läuft (dann NICHT self-hosted verwenden) und ob er
Steps enthält, die Host-weite Änderungen vornehmen (Netzwerk, Firewall,
System-Pakete) — solche Steps müssen wie `harden-runner` auf
`ubuntu-latest`-Läufe beschränkt bleiben.

## Rollback

```bash
ssh armserver "cd ~/actions-runner && sudo ./svc.sh stop && sudo ./svc.sh uninstall"
RUNNER_ID=$(gh api repos/arn0ld87/agora/actions/runners -q '.runners[] | select(.name=="meinserver-arm64") | .id')
gh api --method DELETE "repos/arn0ld87/agora/actions/runners/${RUNNER_ID}"
```

## Siehe auch

- [`docs/runbooks/e2e-required-check.md`](e2e-required-check.md)
- [`.github/workflows/docker-image.yml`](../../.github/workflows/docker-image.yml)

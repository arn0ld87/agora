# Self-hosted Runner `meinserver-arm64`

Ein GitHub-Actions-Self-hosted-Runner läuft als Docker-Container
(`myoung34/github-runner`) auf `armserver` (Tailscale, arm64) und ist im Repo
`arn0ld87/agora` registriert.

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

4. Der Runner läuft in einem Docker-Container (`myoung34/github-runner`),
   nicht direkt auf dem Host-Betriebssystem — Prozess- und Dateisystem-Zugriff
   eines Jobs sind damit vom restlichen `armserver`-Host (Compose-Stacks,
   Vaultwarden, n8n u. a.) isoliert.

**Bekannte, noch offene Lücke:** Der Container ist persistent
(`--restart unless-stopped`), nicht ephemer. Ein Job bekommt zwar ein vom
Host getrenntes Dateisystem, aber *innerhalb* des Containers bleibt Zustand
zwischen aufeinanderfolgenden Jobs erhalten (kein Reset pro Job). Für volle
Job-zu-Job-Isolation müsste der Container mit `EPHEMERAL=true` laufen plus
einem Wrapper, der ihn nach jedem Job neu erstellt (der Container dereg-
istriert sich sonst nach einem Job und bleibt dann offline). Das ist noch
nicht umgesetzt — Tracking: siehe „Erweiterung auf weitere Jobs" unten,
kein weiterer Job darf ergänzt werden, ohne diese Abwägung erneut zu treffen.

## Runner-Details

- Name: `meinserver-arm64`
- Labels: `self-hosted`, `Linux`, `ARM64`, `meinserver`
- Host: `armserver` (SSH-Alias)
- Betrieb: Docker-Container `gh-runner-meinserver-arm64`
  (Image `myoung34/github-runner:latest`), `--restart unless-stopped`
- Registrierung: kurzlebiges Registrierungstoken (`RUNNER_TOKEN`, 1 Std.
  gültig) bei Container-Start — bewusst kein dauerhaftes PAT im Container.
  Bei Neuerstellung des Containers muss ein frisches Token besorgt werden
  (siehe „Neu erstellen" unten).
- Zweck: native arm64-Docker-Builds ohne QEMU-Emulation; potenziell künftig
  Tests gegen bereits laufende interne Dienste (Neo4j/Ollama auf meinserver)

## Erweiterung auf weitere Jobs

Bevor ein weiterer Job auf diesen Runner umgestellt wird: prüfen, ob er auf
`pull_request` von Forks läuft (dann NICHT self-hosted verwenden) und ob er
Steps enthält, die Host-weite Änderungen vornehmen (Netzwerk, Firewall,
System-Pakete) — solche Steps müssen wie `harden-runner` auf
`ubuntu-latest`-Läufe beschränkt bleiben.

## Neu erstellen (z. B. nach Image-Update oder Registrierungsverlust)

```bash
ssh armserver "docker rm -f gh-runner-meinserver-arm64"
TOKEN=$(gh api --method POST repos/arn0ld87/agora/actions/runners/registration-token -q .token)
ssh armserver "docker run -d \
  --name gh-runner-meinserver-arm64 \
  --restart unless-stopped \
  -e REPO_URL=https://github.com/arn0ld87/agora \
  -e RUNNER_NAME=meinserver-arm64 \
  -e RUNNER_TOKEN='$TOKEN' \
  -e LABELS=self-hosted,arm64,meinserver \
  -e RUNNER_WORKDIR=/tmp/gh-runner-work \
  -v /tmp/gh-runner-work:/tmp/gh-runner-work \
  myoung34/github-runner:latest"
```

## Rollback (Runner komplett entfernen)

```bash
ssh armserver "docker rm -f gh-runner-meinserver-arm64"
RUNNER_ID=$(gh api repos/arn0ld87/agora/actions/runners -q '.runners[] | select(.name=="meinserver-arm64") | .id')
gh api --method DELETE "repos/arn0ld87/agora/actions/runners/${RUNNER_ID}"
```

## Siehe auch

- [`docs/runbooks/e2e-required-check.md`](e2e-required-check.md)
- [`.github/workflows/docker-image.yml`](../../.github/workflows/docker-image.yml)

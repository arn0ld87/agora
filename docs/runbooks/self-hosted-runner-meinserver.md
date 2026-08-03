# Self-hosted Runner `meinserver-arm64` — außer Betrieb

> **Status: außer Betrieb genommen am 2026-08-03.** Der Runner wird von keinem
> Workflow mehr adressiert. `.github/workflows/docker-image.yml` nutzt für alle
> Trigger `ubuntu-latest`.
>
> Dieses Dokument bleibt erhalten, weil die Abwägung darunter jedes Mal erneut
> zu treffen ist, wenn ein self-hosted Runner an diesem Repository erwogen wird.

## Warum außer Betrieb

**Er hat nie funktioniert.** Der Runner lief als Docker-Container ohne
gemounteten Docker-Socket. Das Verzeichnis `/var/run/docker.sock` existierte im
Container schlicht nicht, `docker version` meldete dort kein Server-Feld. Damit
brach `Set up Docker Buildx` ausnahmslos ab:

```
ERROR: failed to initialize builder …: Cannot connect to the Docker daemon
at unix:///var/run/docker.sock. Is the docker daemon running?
```

Sein einziger dokumentierter Zweck war „native arm64-Docker-Builds ohne QEMU" —
also genau das, was ohne Docker-Zugriff unmöglich ist. Praktische Folge: Seit
Einrichtung schlug **jeder** `push`-auf-`main`-Lauf des Docker-Workflows fehl,
und es gelangte kein Image mehr nach GHCR. Aufgefallen ist das nicht, weil der
`publish`-Job ohnehin nur auf Release-/RC-Branches und Tags scharf ist und die
Deployments auf `armserver` lokal bauen.

**Die naheliegende Reparatur wäre schlimmer gewesen als der Defekt.** Ein
`-v /var/run/docker.sock:/var/run/docker.sock` hätte den Runner funktionsfähig
gemacht und ihm zugleich Root-äquivalenten Zugriff auf `armserver` gegeben —
denselben Host, der Vaultwarden, Stalwart, n8n und den produktiven Agora-Stack
trägt. Damit wäre auch die Isolationszusage aus Punkt 4 der alten Fassung
hinfällig gewesen: Ein Container mit Host-Docker-Socket ist gegenüber dem Host
nicht isoliert, er kontrolliert ihn.

**Sein Zweck war ohnehin nicht belegt.** `build-only` reicht sein Image an
`prod-proxy-smoke` weiter, und der läuft auf `ubuntu-latest` — ein
arm64-Artefakt startet dort nicht. `publish` baut ebenfalls auf `ubuntu-latest`,
das Image in GHCR war also immer amd64, und die Deployments auf `armserver`
bauen lokal statt aus der Registry. Für die Kette build → smoke → publish gab es
keinen Konsumenten der arm64-Variante; der Mangel fiel nur nie auf, weil
`build-only` stets vorher abbrach.

Der Workflow läuft deshalb vollständig auf `ubuntu-latest`. Werden echte
arm64-Images gebraucht, gehört das als Multi-Platform-Build
(`platforms: linux/amd64,linux/arm64`) in den publish-Job — nicht als
abweichender Runner für einen einzelnen Job. GitHub-gehostete arm64-Runner
(`ubuntu-24.04-arm`) wären dafür ebenfalls verfügbar und für öffentliche
Repositories kostenfrei.

## Sicherheitskontext (public Repo) — weiterhin gültig

`agora` ist ein **public** Repository. Self-hosted Runner auf public Repos sind
laut GitHub ein bekanntes Risiko: Fork-PRs können Code ausführen, der dann auf
dem eigenen Host läuft. `armserver` betreibt daneben produktive Dienste
(Compose-Stack hinter Traefik, Neo4j, Ollama, Vaultwarden, Stalwart, n8n) — ein
kompromittierter CI-Job hätte Netzwerkzugriff auf diese Dienste.

Der Schutz beruhte auf einer einzigen Zeile: dem `runs-on`-Ausdruck, der
`pull_request` auf `ubuntu-latest` umleitete. Eine spätere Ergänzung eines
Triggers — `pull_request_target`, ein zusätzlicher Job, eine Umstellung im
Rahmen eines unrelated Refactors — hätte diesen Schutz aufgehoben, ohne dass es
jemandem beim Review auffallen muss.

**Wer den Runner wieder aufsetzen will, muss zuvor beantworten:**

1. Warum genügen GitHub-gehostete Runner nicht — inklusive `ubuntu-24.04-arm`,
   falls es um arm64 geht?
2. Wie wird verhindert, dass je ein `pull_request`-artiger Trigger auf dem
   Runner landet — nicht nur heute, sondern auch nach künftigen Änderungen?
3. Bekommt der Runner Docker-Zugriff? Falls ja: Warum ist Root-Äquivalenz auf
   einem Host mit Vaultwarden vertretbar, und welche Alternative (rootless
   Docker, ephemere VM, dedizierter Host ohne andere Dienste) wurde verworfen?
4. Ist der Container ephemer (`EPHEMERAL=true` plus Wrapper, der ihn nach jedem
   Job neu erstellt)? Die persistente Variante hält Zustand zwischen Jobs.

## Rückbau

Container entfernen und Registrierung bei GitHub löschen:

```bash
ssh armserver "docker rm -f gh-runner-meinserver-arm64"
RUNNER_ID=$(gh api repos/arn0ld87/agora/actions/runners \
  -q '.runners[] | select(.name=="meinserver-arm64") | .id')
gh api --method DELETE "repos/arn0ld87/agora/actions/runners/${RUNNER_ID}"
```

Solange kein Workflow ihn adressiert, richtet ein noch laufender Runner keinen
Schaden an — er bekommt schlicht keine Jobs mehr zugewiesen. Der Rückbau ist
trotzdem angeraten, damit kein registrierter Runner mit veraltetem Image und
offener Registrierung stehen bleibt.

## Siehe auch

- [`docs/runbooks/e2e-required-check.md`](e2e-required-check.md)
- [`.github/workflows/docker-image.yml`](../../.github/workflows/docker-image.yml)

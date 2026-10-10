# Deploy aus GHCR: Images ziehen statt bauen

**Stand:** 2026-09-28 (#1708)

Ein Host kann Agora aus fertigen Images starten, statt `agora` und `nginx` selbst zu bauen. Das lohnt sich vor allem auf ausgelasteten Hosts: Dort bricht der lokale BuildKit-Build ab, weil die Build-Session am Healthcheck stirbt.

## Was die CI liefert

`.github/workflows/docker-image.yml` publiziert zwei Images:

| Image | Dockerfile-Stage | Inhalt |
|---|---|---|
| `ghcr.io/arn0ld87/agora` | `prod` | Backend, Gunicorn, CLI-Provider |
| `ghcr.io/arn0ld87/agora-proxy` | `proxy` | nginx und Frontend-Bundle, **ohne** Build-Time-Token |

| Tag | Entsteht bei | Gate | Beweglich? |
|---|---|---|---|
| `sha-<7>` | jedem Publish | mindestens `build-only` | nein |
| `edge` | grünem `main`-Push | `build-only` (Build, Trivy beider Images) | ja |
| `vX.Y.Z` | Release-Tag | zusätzlich Reverse-Proxy-Smoke | nein |
| `latest` | Release-Tag | zusätzlich Reverse-Proxy-Smoke | ja |

`edge` und `sha-<7>` von `main` haben **keinen** Smoke durchlaufen. Für Releases gilt weiter der Smoke.

Beide Images tragen eine Build-Provenance-Attestation. Sie belegt Commit, Workflow und Runner (Details: [`../sbom-provenance.md`](../sbom-provenance.md)). Beide Images sind Multi-Arch-Manifeste (`linux/amd64` und `linux/arm64`); armserver ist aarch64 und zieht die arm64-Variante. Die Attestation gilt für den Digest der Manifest-Liste.

## Einmalig: Pakete öffentlich schalten

GHCR legt neue Pakete privat an, auch wenn das Repository öffentlich ist. Solange das so bleibt, braucht jeder Pull ein Token mit `read:packages`.

Für `agora` **und** `agora-proxy`: GitHub → Profil → Packages → Paket → Package settings → Danger Zone → Change visibility → Public. Die Verknüpfung zum Repository entsteht automatisch über das Label `org.opencontainers.image.source`.

Prüfen, ob ein anonymer Pull geht:

```bash
docker logout ghcr.io
docker pull ghcr.io/arn0ld87/agora-proxy:edge
```

## Deploy

1. **Tag bestimmen.** Den Commit nehmen, der deployt werden soll, und prüfen, ob sein Lauf von `docker-image.yml` grün ist:

   ```bash
   SHA=$(git rev-parse origin/main)
   gh run list --workflow docker-image.yml --commit "$SHA" --json conclusion,event --jq '.[] | select(.event=="push")'
   export AGORA_IMAGE_TAG=sha-${SHA:0:7}
   ```

   `edge` oder `latest` nicht als `AGORA_IMAGE_TAG` setzen. Mit einem beweglichen Tag lässt sich hinterher nicht mehr sagen, was lief, und ein Rollback braucht einen festen Tag.

2. **Herkunft prüfen** (gh 2.49+, auf dem Host oder lokal):

   ```bash
   gh attestation verify oci://ghcr.io/arn0ld87/agora:$AGORA_IMAGE_TAG --repo arn0ld87/agora
   gh attestation verify oci://ghcr.io/arn0ld87/agora-proxy:$AGORA_IMAGE_TAG --repo arn0ld87/agora
   ```

3. **Bind-Mount-Quellverzeichnisse vorbereiten.** Die Compose-Dateien binden
   `./backend/data`, `./backend/instance`, `./backend/uploads` und
   `./backend/.cache/huggingface` aus dem Arbeitsverzeichnis ein. Fehlt ein
   Quellverzeichnis, legt der Docker-Daemon es als `root:root` an, und der
   Container-User (uid 1000) kann nicht hineinschreiben — Symptome sind
   `PermissionError` auf `/home/agora/.cache/huggingface/hub` bzw.
   `TwhinCacheError` beim Simulationsstart. Getrackte `.gitkeep`-Platzhalter
   gibt es nur für `backend/data` und `backend/.cache/huggingface`;
   `backend/instance` und `backend/uploads` legt das Deployment an (die
   Container-CI bereitet `uploads` per ACL vor). Auch ein als root oder mit
   fremder UID erstellter Checkout besitzt die Verzeichnisse nicht als uid 1000
   — deshalb Besitz/Beschreibbarkeit prüfen und reparieren, statt sich auf den
   Klon zu verlassen:

   ```bash
   for d in backend/data backend/instance backend/uploads backend/.cache/huggingface; do
     mkdir -p "$d"
     [ "$(stat -c '%u' "$d")" = "1000" ] || sudo chown -R 1000:1000 "$d"
   done
   ```

   Ohne Besitzerwechsel geht auch `sudo setfacl -m u:1000:rwx <verzeichnis>`
   (dasselbe Muster nutzt die CI für `backend/uploads`). Im Container hilft kein
   `chown` — der Stack läuft mit `cap_drop: ALL`.
   Details: [`../deployment-dev.md`](../deployment-dev.md), Abschnitt
   „Bind-Mount-Rechte".

4. **Ziehen und starten.** Das Overlay `deploy/compose/docker-compose.ghcr.yml` kommt als **letztes** `-f`, damit `build: !reset` die `build`-Blöcke der vorherigen Dateien entfernt. Es definiert nginx nicht selbst, deshalb muss vorher ein Overlay stehen, das den Service anlegt (`deploy/compose/docker-compose.prod-with-proxy.yml` oder ein Host-Overlay):

   ```bash
   COMPOSE="docker compose \
     -f docker-compose.yml \
     -f docker-compose.prod.yml \
     -f deploy/compose/docker-compose.prod-with-proxy.yml \
     -f deploy/compose/docker-compose.ghcr.yml"

   $COMPOSE config --format json | jq -r '.services.agora.image, .services.nginx.image'
   $COMPOSE pull agora nginx
   $COMPOSE up -d --no-build agora nginx
   ```

   Nur `agora` und `nginx` neu starten. Ein `down` würde Neo4j und Redis mitreißen.

   Weitere Overlays wie `deploy/compose/docker-compose.codex-cli.yml` oder das Host-Overlay stehen **vor** dem GHCR-Overlay. Die Reihenfolge der übrigen Dateien bleibt, wie sie ist.

5. **Verifizieren:**

   ```bash
   docker inspect agora --format '{{.Config.Image}}'
   curl -fsS http://localhost:${AGORA_PROXY_PORT:-8080}/health
   ```

   Das Image trägt die OCI-Labels `org.opencontainers.image.revision` (voller Commit-SHA) und `org.opencontainers.image.version`. Der laufende Stand lässt sich damit ohne Reflog-Abgleich ablesen.

## Rollback

`AGORA_IMAGE_TAG` auf den vorherigen `sha-<7>`-Tag setzen, dann Schritt 4 wiederholen. Es wird nichts gebaut, der Rollback dauert so lange wie der Pull.

Datenmigrationen macht das nicht rückgängig. Hat der neue Stand eine Alembic-Revision angewendet, gelten die Rückwege aus dem jeweiligen Umstellungs-Runbook.

## Zurück zum lokalen Build

Das GHCR-Overlay weglassen und mit `--build` starten wie bisher. Das ist auch der Weg, wenn das Frontend-Bundle ein Build-Time-Token tragen soll (`ALLOW_BUILD_TIME_TOKEN=true`): Das publizierte Proxy-Image hat keins, die Anmeldung läuft zur Laufzeit.

## Grenzen

- Auf `main` ist das Gate Build plus Trivy, nicht der End-to-End-Smoke. Ein Image kann sauber bauen und trotzdem nicht starten. Deshalb den Health-Check aus Schritt 5 nicht auslassen und den vorherigen Tag für den Rollback notieren.
- Host-spezifische Build-Args außer den Dockerfile-Defaults werden ignoriert, weil nichts gebaut wird.
- Die Images sind öffentlich. Sie enthalten keine Secrets. Konfiguration und Schlüssel kommen weiter aus `.env` und den Mounts des Hosts.

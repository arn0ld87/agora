# Multi-Stage Dockerfile für Agora.
#
# Targets:
#   dev   — Default, identisch mit der ursprünglichen Single-Stage-Variante.
#           Enthält Bun + uv + alle Dev-Dependencies, lädt das Repo per
#           Bind-Mount und startet `bun run dev` (Vite + Flask).
#   prod  — schlanke Runtime: gebautes Frontend-Bundle, gunicorn vor Flask.
#           Kein Vite, kein Bun, kein curl, kein Bind-Mount erwartet.
#
# Auswahl im Compose über `target: dev` / `target: prod`. Default-
# Compose nutzt `dev`. Für Produktions-Setups siehe
# `docker-compose.prod.yml`.

# ---------- shared base ----------
# Digest-Stand 2026-07-14 (python:3.14, buildpack-deps:trixie). Bump am
# 2026-07-31 im Zuge von #772: senkt die HIGH/CRITICAL-Findings der Build-
# Stages von 129 auf 32 und beseitigt die einzige CRITICAL (CVE-2026-56367,
# imagemagick). Betrifft nur base/dev/frontend-build/backend-build — die
# Prod-Stage erbt von python:3.14-slim und übernimmt per COPY nur .venv+dist.
FROM python:3.14@sha256:5f1cdbcab9a50594a79502dd73e885456d2a2fc31f1a1fa18484815b37ee9152 AS base

RUN apt-get update \
  && apt-get install -y --no-install-recommends curl unzip \
  && rm -rf /var/lib/apt/lists/*

# bun auf Digest gepinnt (1.3.14, Stand 2026-08-03). Der Rolling-Tag `1`
# invalidierte diese Layer — und damit jede abgeleitete Stage — bei jedem
# Upstream-Push, auch ohne Änderung im Repo.
COPY --from=oven/bun:1.3.14@sha256:e10577f0db68676a7024391c6e5cb4b879ebd17188ab750cf10024a6d700e5c4 /usr/local/bin/bun /usr/local/bin/bun
# uv ebenfalls auf Digest gepinnt. Der Digest ist der Manifest-List-Digest,
# nicht der einer einzelnen Plattform — die Liste trägt linux/amd64 und
# linux/arm64, das Image bleibt damit auf beiden Build-Hosts verwendbar.
COPY --from=ghcr.io/astral-sh/uv:0.9.26@sha256:9a23023be68b2ed09750ae636228e903a54a05ea56ed03a934d00fe9fbeded4b /uv /uvx /bin/

# Große CUDA-Wheels (cudnn ~700 MB, nvshmem ~300 MB) sprengen den
# uv-Default von 30 s auf langsamen Leitungen.
ENV UV_HTTP_TIMEOUT=1800
ENV UV_HTTP_RETRIES=5

# Die uv- und bun-Installationsschritte unten nutzen `--mount=type=cache`.
# Ein Cache-Mount ist ein eigenes Dateisystem, also kann uv die Wheels nicht
# per Hardlink in die venv legen; ohne diese Zeile warnt jeder Build und
# fällt ohnehin auf Copy zurück.
ENV UV_LINK_MODE=copy

# nltk >= 3.10 installiert einen Import-Hook (nltk/inisec.py), der jeden von
# nltk ausgelösten Import blockiert, dessen Modul unterhalb des CWD liegt.
# WORKDIR ist /app und die venv liegt unter /app/backend/.venv — damit gilt
# *jedes* Paket der venv als "aus dem CWD" und `regex`/`defusedxml` werden
# blockiert, sobald `unstructured` beim Parsen nltk lädt. Der Hook ist
# Defense-in-Depth gegen CWD-Import-Hijacking, nicht der eigentliche Fix für
# GHSA-p4gq-832x-fm9v (Path Traversal in nltk.data.load()) — der bleibt aktiv.
# Siehe docs/dependency-risk-register.md, Abschnitt "nltk-Baseline".
ENV NLTK_DISABLE_IMPORT_SECURITY=1

ENV TZ=Europe/Berlin

WORKDIR /app
RUN useradd -m -u 1000 agora \
  && mkdir -p /app/backend/uploads /app/backend/logs \
  && chown -R agora:agora /app

# ---------- codex-cli (Binary-Bezug, landet per COPY in dev und prod) ----------
# Der codex_cli-Provider (#1405/#1406) ruft das ``codex``-Binary als Subprozess
# auf; ``is_codex_cli_available()`` macht ein ``shutil.which("codex")`` **im
# Container**. Eine Installation auf dem Host hilft also nicht — ohne diese
# Stage meldet die Provider-Probe dauerhaft "codex-CLI nicht im PATH gefunden"
# und das ChatGPT-Abo bleibt unbenutzbar, obwohl der Provider vollstaendig
# implementiert ist.
#
# Eigene Stage statt zweier Installationen, weil ``prod`` nicht von ``base``
# erbt: beide Ziel-Stages holen sich dasselbe verifizierte Binary per COPY,
# und der Download passiert im Build genau einmal.
#
# Groesse ehrlich benannt: ~86 MB als tar.gz, **222 MB entpackt** — das
# Laufzeit-Image waechst entsprechend. Das ist der Preis dafuer, das
# ChatGPT-Abo ueberhaupt aus dem Container heraus nutzen zu koennen; wer den
# codex_cli-Provider nicht braucht, kann die COPY-Zeilen in dev/prod
# entfernen, ohne sonst etwas anzufassen.
#
# codex ist seit dem Rust-Rewrite ein statisch gelinktes musl-Binary — kein
# Node, keine Laufzeitabhaengigkeiten, laeuft unveraendert im slim-Image.
FROM base AS codex-cli

# Version und Hashes bewusst gepinnt (dasselbe Muster wie die FROM-Digests):
# ein ungeprueftes Binary aus dem Netz gehoert nicht ins Laufzeit-Image.
# Die Hashes stammen aus dem ``digest``-Feld der GitHub-Releases-API und
# muessen bei einem Versionsbump beide mitgezogen werden.
ARG CODEX_VERSION=rust-v0.153.2
ARG CODEX_SHA256_AMD64=e8cd1160071f725d2a10cab81073dd6818fc8b096372125d27ef6e66fdf0979e
ARG CODEX_SHA256_ARM64=878693f9b370320ea21793f99ea1f5687b7d9aa1f2c733de693d9ec0baa4e62a
# TARGETARCH befuellt BuildKit nur im Multi-Platform-Kontext; ein schlichtes
# `docker compose build` laesst die Variable LEER. Ein Default darauf waere
# eine Falle: mit `=amd64` zog ein aarch64-Server das x86_64-Binary und der
# Build brach erst am abschliessenden `codex --version` mit exit 126 ab
# ("cannot execute"), nachdem Download und Hash-Pruefung sauber durchliefen.
#
# `uname -m` ist die verlaessliche Quelle: Der Build laeuft nativ auf der
# Zielarchitektur, und unter QEMU-Emulation (buildx --platform) meldet uname
# ebenfalls die Ziel- und nicht die Hostarchitektur. TARGETARCH bleibt als
# Override vorne, falls BuildKit es doch setzt — bewusst ohne Default.
ARG TARGETARCH

RUN set -eux; \
    case "${TARGETARCH:-}" in \
      amd64) _arch=x86_64 ;; \
      arm64) _arch=aarch64 ;; \
      *) case "$(uname -m)" in \
           x86_64)        _arch=x86_64 ;; \
           aarch64|arm64) _arch=aarch64 ;; \
           *) echo "codex: nicht unterstuetzte Architektur '$(uname -m)'" >&2; exit 1 ;; \
         esac ;; \
    esac; \
    case "${_arch}" in \
      x86_64)  _sha="${CODEX_SHA256_AMD64}" ;; \
      aarch64) _sha="${CODEX_SHA256_ARM64}" ;; \
    esac; \
    _url="https://github.com/openai/codex/releases/download/${CODEX_VERSION}/codex-${_arch}-unknown-linux-musl.tar.gz"; \
    curl -fsSL --retry 3 --retry-delay 2 -o /tmp/codex.tar.gz "${_url}"; \
    echo "${_sha}  /tmp/codex.tar.gz" | sha256sum -c -; \
    mkdir -p /tmp/codex-extract; \
    tar -xzf /tmp/codex.tar.gz -C /tmp/codex-extract; \
    # Der Tarball traegt das Binary unter wechselndem Namen (mit/ohne
    # Target-Triple); der Fund per find bleibt ueber Releases hinweg stabil.
    _bin="$(find /tmp/codex-extract -type f -name 'codex*' | head -n1)"; \
    test -n "${_bin}"; \
    install -m 0755 "${_bin}" /usr/local/bin/codex; \
    rm -rf /tmp/codex.tar.gz /tmp/codex-extract; \
    codex --version

# ---------- dev (default) ----------
FROM base AS dev

# ``codex`` fuer den codex_cli-Provider. Die Anmeldung selbst liegt NICHT im
# Image: ``codex login`` legt sie unter ``$CODEX_HOME`` (Default ``~/.codex``)
# ab, und die wird zur Laufzeit als read-only Volume hereingereicht — siehe
# docker-compose.yml. Ein Abo-Token gehoert in keine Image-Schicht.
COPY --from=codex-cli /usr/local/bin/codex /usr/local/bin/codex

COPY --chown=agora:agora package.json bun.lock ./
COPY --chown=agora:agora frontend/package.json frontend/bun.lock ./frontend/
COPY --chown=agora:agora backend/pyproject.toml backend/uv.lock ./backend/

# Cache-Mounts: ohne sie lädt jede Lockfile-Änderung sämtliche Wheels und
# npm-Tarballs neu aus dem Netz — auch die unveränderten. Der Backend-Baum
# zieht über camel-oasis → sentence-transformers → torch mehrere GB CUDA-
# Wheels, das dominiert die Buildzeit nach jedem Dependency-Update.
RUN --mount=type=cache,target=/root/.bun/install/cache,sharing=locked \
    --mount=type=cache,target=/root/.cache/uv,sharing=locked \
    bun install --frozen-lockfile \
  && bun install --frozen-lockfile --cwd frontend \
  && cd backend && uv sync --frozen \
  && chown -R agora:agora /app

COPY --chown=agora:agora . .

USER agora

ENV FLASK_HOST=0.0.0.0

EXPOSE 5173 5001

# start-period deckt den kompletten Kaltstart ab: in dieser Stage bootet
# zusaetzlich der Vite-Dev-Server, gemessen ~60 s bis /readyz antwortet
# (armserver, 2026-08-30). Mit den vorherigen 5 s zaehlte Docker die
# Startup-Fehlschlaege schon als echte Fehler — der Container kippte fuer
# ~20 s auf `unhealthy`, bevor er healthy wurde. Das ist kein kosmetisches
# Problem: `depends_on: condition: service_healthy` und jedes Monitoring,
# das auf den Status schaut, sehen darin einen Ausfall. Fehlschlaege
# innerhalb der start-period lassen den Status auf `starting` stehen.
HEALTHCHECK --interval=30s --timeout=10s --start-period=90s --retries=3 \
  CMD curl -f http://localhost:5001/readyz || exit 1

CMD ["bun", "run", "dev"]

# ---------- frontend-build (frontend bundle only) ----------
FROM base AS frontend-build

# Reihenfolge ist bewusst: erst Dependencies installieren, dann das
# Token-Gate. Vorher stand der Gate-RUN vor `bun install`, wodurch jede
# Änderung an ALLOW_BUILD_TIME_TOKEN, VITE_AGORA_TOKEN oder VITE_UI_VERSION
# auch die Dependency-Installation invalidierte. Die ARG-Deklarationen
# stehen deshalb ebenfalls erst unten — ein ARG invalidiert den Cache erst
# an der Stelle, an der es verwendet wird.
COPY --chown=agora:agora frontend/package.json frontend/bun.lock ./frontend/
RUN --mount=type=cache,target=/root/.bun/install/cache,sharing=locked \
    cd frontend && bun install --frozen-lockfile

COPY --chown=agora:agora frontend/ ./frontend/

# Build-Time-Token-Gate (F2.1, Sub-Slice 46).
#
# Default: ALLOW_BUILD_TIME_TOKEN=false → der Build ignoriert
# VITE_AGORA_TOKEN, das Frontend-Bundle bekommt einen LEEREN Token-Wert
# einkompiliert. Das Frontend muss den Token zur Laufzeit per
# setAgoraToken() setzen (siehe frontend/src/api/index.ts und das
# UI-Eingabefeld in der App).
#
# Opt-In: ALLOW_BUILD_TIME_TOKEN=true erlaubt das Einbrennen des Tokens
# ins Bundle. Nur sinnvoll für Single-User-Tailnet-Deploys. Caveat:
# wer das Bundle hat, hat den Token. Niemals fuer Public-Internet-Deploys.
#
# Aufruf:
#   docker build --target frontend-build \
#     --build-arg ALLOW_BUILD_TIME_TOKEN=true \
#     --build-arg VITE_AGORA_TOKEN=<token> .
ARG ALLOW_BUILD_TIME_TOKEN=false
ARG VITE_AGORA_TOKEN=""
# Build-Provenance-Marker (Design-Language-Version).
# Wird in main.ts als `import.meta.env.VITE_UI_VERSION` ausgelesen und
# auf `window.__AGORA_UI_VERSION__` gespiegelt. Sichtbar in Browser-DevTools,
# damit Rollouts/Rollbacks ohne Bundle-Hash-Vergleich identifizierbar sind.
ARG VITE_UI_VERSION="v4"
# ENV VITE_AGORA_TOKEN wird bewusst NICHT gesetzt — ein ENV-Befehl würde
# den ARG-Wert im RUN-Block überschreiben und das Gate wäre wirkungslos.
# Vite liest VITE_* zur Build-Zeit aus dem Shell-Kontext von bun run build;
# Gate-Entscheidung und Build laufen deshalb in einer Shell, der Token-Wert
# bleibt eine Shell-Variable und wird in keine Datei geschrieben.
RUN _token="${VITE_AGORA_TOKEN:-}" && \
    if [ "$ALLOW_BUILD_TIME_TOKEN" = "true" ] && [ -n "$_token" ]; then \
      echo "ALLOW_BUILD_TIME_TOKEN=true: VITE_AGORA_TOKEN wird ins Bundle einkompiliert."; \
    else \
      echo "ALLOW_BUILD_TIME_TOKEN=false (Default): Frontend-Bundle bekommt leeren Token. Runtime-Login erforderlich."; \
      _token=""; \
    fi && \
    echo "VITE_UI_VERSION=${VITE_UI_VERSION:-v4} (Build-Provenance)." && \
    cd frontend && \
    VITE_AGORA_TOKEN="$_token" VITE_UI_VERSION="${VITE_UI_VERSION:-v4}" bun run build

# ---------- backend-build (production Python environment only) ----------
FROM base AS backend-build

COPY --chown=agora:agora backend/pyproject.toml backend/uv.lock ./backend/
# Backend-Dependencies ohne Dev-Group und strikt aus uv.lock installieren.
# Der Cache-Mount teilt sich den Wheel-Cache mit der dev-Stage: torch und die
# CUDA-Wheels werden pro Host einmal geladen statt einmal pro Stage.
RUN --mount=type=cache,target=/root/.cache/uv,sharing=locked \
    cd backend && uv sync --frozen --no-dev \
  && chown -R agora:agora /app

# ---------- prod ----------
# Digest-Stand 2026-07-14 (python:3.14.6-slim-trixie). Bump am 2026-07-31 im
# Zuge von #772. Reine Image-Hygiene: alter wie neuer Digest sind Trivy-sauber
# (0 HIGH/CRITICAL mit Fix). Das Image enthält weder wheel noch jaraco.context
# — es liefert nur pip aus (CPython-Build mit --with-ensurepip), weshalb die
# beiden #772-CVEs nie aus dieser Schicht stammten. Siehe
# docs/2026-07-31-issue-772-cve-basisimage-research.md.
FROM python:3.14-slim@sha256:cad9a2c871761c413caa6fdd6441c783451e740a48aaeba60ae62a8b53525ef6 AS prod

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    FLASK_HOST=0.0.0.0 \
    PATH="/app/backend/.venv/bin:$PATH" \
    NLTK_DISABLE_IMPORT_SECURITY=1

WORKDIR /app

# apt-get upgrade fährt die Debian-Security-Updates ein, die im gepinnten
# Basisimage-Digest noch fehlen (#1328). Hintergrund: Debian veröffentlicht
# Paket-Fixes deutlich früher, als die Docker-Official-Images nachgebaut
# werden. Konkreter Anlass war CVE-2026-53615 (util-linux, Integer-Overflow
# in libblkid/src/partitions/dos.c): der Fix 2.41.5-0+deb13u1 lag am
# 2026-08-17 im trixie-Repo, während sowohl der hier gepinnte Digest als
# auch der zu dem Zeitpunkt aktuellste python:3.14-slim weiterhin 2.41-5
# auslieferten. Der Trivy-Scan lief dadurch acht Läufe am Stück rot, ohne
# dass ein Digest-Bump das behoben hätte.
#
# Die Zeile ist bewusst allgemein und nicht auf util-linux verengt: sonst
# wiederholt sich derselbe Dauerrot-Zustand bei der nächsten Distro-CVE.
# Der Digest-Pin oben bleibt die reproduzierbare Ausgangsbasis; die
# Security-Patches darauf sind per Definition zeitabhängig.
#
# Ergaenzung 2026-09-04 (CVE-2026-14456, openssl/libssl3t64/
# openssl-provider-legacy 3.5.6-1~deb13u2 -> 3.5.7-1~deb13u2): Dass diese
# RUN-Zeile existiert, genuegt nicht — der Build-Job zieht `cache-from:
# type=gha`, und solange FROM-Digest und Instruktion unveraendert bleiben,
# serviert BuildKit den *alten* apt-Layer. `apt-get upgrade` laeuft dann gar
# nicht neu und der Scan bleibt rot, obwohl der Fix laengst im trixie-Repo
# liegt. Der Digest-Bump oben ist deshalb hier kein Ersatz fuer den Upgrade,
# sondern sein Ausloeser: neuer FROM-Digest = invalidierter Layer = frischer
# apt-Lauf. Bei der naechsten Distro-CVE ist der Digest-Bump wieder das
# Mittel, um diese Zeile erneut scharf zu stellen.
RUN apt-get update \
  && apt-get upgrade -y \
  && apt-get install -y --no-install-recommends tzdata \
  && rm -rf /var/lib/apt/lists/* \
  && ln -snf /usr/share/zoneinfo/Europe/Berlin /etc/localtime \
  && echo "Europe/Berlin" > /etc/timezone

# pip aus dem Runtime-Image entfernen (#1410). pip 26.2.1 bringt in
# site-packages/pip/_vendor laut vendor.txt msgpack==1.1.2 und
# setuptools==70.3.0 mit; Trivy meldet beide als HIGH (GHSA-6v7p-g79w-8964
# bzw. CVE-2025-47273) und blockiert damit build-only. Ueber uv.lock sind sie
# nicht erreichbar — die venv fuehrt setuptools 83.0.0 und gar kein msgpack.
#
# Das prod-Image braucht pip zur Laufzeit nicht: die venv wird fertig aus
# backend-build kopiert und enthaelt selbst kein pip, gunicorn startet aus
# /app/backend/.venv/bin, und der HEALTHCHECK nutzt urllib. Die einzigen
# pip-Vorkommen im Backend sind Texte in Fehlermeldungen, keine Aufrufe.
# Entfernen statt .trivyignore, weil das die Funde beseitigt statt sie zu
# unterdruecken — und nebenbei Angriffsflaeche und Imagegroesse reduziert.
# Die dev-Stage bleibt unberuehrt und behaelt pip.
RUN rm -rf /usr/local/lib/python3.14/site-packages/pip \
           /usr/local/lib/python3.14/site-packages/pip-*.dist-info \
           /usr/local/bin/pip /usr/local/bin/pip3 /usr/local/bin/pip3.14

ENV TZ=Europe/Berlin

RUN useradd -m -u 1000 -s /usr/sbin/nologin agora \
  && mkdir -p /app/backend/uploads /app/backend/logs /app/frontend/dist /home/agora/.cache /home/agora/.gunicorn \
  && chown -R agora:agora /app /home/agora

COPY --chown=agora:agora --from=backend-build /app/backend/.venv ./backend/.venv
COPY --chown=agora:agora backend/pyproject.toml backend/uv.lock backend/run.py backend/wsgi.py backend/gunicorn.conf.py ./backend/
COPY --chown=agora:agora backend/app ./backend/app
COPY --chown=agora:agora backend/scripts ./backend/scripts
# E2E-Stub-Snapshot: llm_e2e_stub.py liest die Pflichtabschnitte aus dieser Datei.
# Der Fallback in _required_sections() greift wenn die Datei fehlt, aber
# die Primär-Quelle liegt hier — damit sind Snapshot-Drift-Tests (M11.8b) auch
# im prod-Image möglich (z. B. via /api/status-Erweiterungen).
COPY --chown=agora:agora backend/tests/eval/snapshots ./backend/tests/eval/snapshots
COPY --chown=agora:agora --from=frontend-build /app/frontend/dist ./frontend/dist

# ``codex`` fuer den codex_cli-Provider — siehe Kommentar an der
# codex-cli-Stage. Bewusst root:root und 0755: das Binary ist Laufzeitcode,
# kein Nutzdatum, und ``agora`` braucht darauf nur Ausfuehrungsrecht.
# Die Anmeldung kommt zur Laufzeit per read-only Volume, nie aus dem Image.
COPY --from=codex-cli /usr/local/bin/codex /usr/local/bin/codex

USER agora

EXPOSE 5001

# Kuerzer als in der dev-Stage — hier faellt der Vite-Boot weg, gunicorn
# und die Python-Imports brauchen aber ebenfalls deutlich mehr als 5 s.
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
  CMD ["python", "-c", "import sys; from urllib.request import urlopen; sys.exit(0 if urlopen('http://localhost:5001/readyz', timeout=5).status == 200 else 1)"]

# Gunicorn vor Flask mit gevent-Worker (non-blocking SSE).
# Direkter Binary-Aufruf statt `uv run` — `uv run` würde bei jedem
# Container-Start einen `.venv`-Sync versuchen und am read-only Rootfs
# scheitern.
#
# Konfiguration (workers, preload, timeouts, post_fork-Hook) liegt in
# backend/gunicorn.conf.py. Der post_fork-Hook resetet vererbte
# Neo4j/Redis-Pool-Sockets im Child — siehe Datei-Header dort. Damit ist
# --preload auch unter -k gevent sicher; os.register_at_fork allein war
# es nicht (gevent monkey-patcht os.fork).
#
# HARDSTOP --workers 1 (Code-Review 2026-05-17, Finding 1.2) bleibt
# bestehen, ist aber jetzt in der conf-Py dokumentiert.
#
# Issue #529: App-Target ist wsgi:app (NICHT mehr app:create_app()), weil
# wsgi.py als allererstes Statement gevent.monkey.patch_all() ausführt.
# Ohne diese Reihenfolge importiert --preload requests/urllib3/ssl mit
# ungepatchtem socket → RecursionError in jedem HTTP-Call.
CMD ["/app/backend/.venv/bin/gunicorn", \
     "--config", "/app/backend/gunicorn.conf.py", \
     "wsgi:app"]

# ---------- proxy (nginx-Sidecar mit eingebackenem Frontend-Bundle) ----------
FROM nginx:alpine@sha256:72ba65eb42c10344912a84ff42408db7d34f2feb642204570ab8fc5ffd29f1d3 AS proxy
# Alpine-Pakete auf Repo-Stand heben, solange das Base-Image hinterherhinkt:
# CVE-2026-33630 (c-ares < 1.34.8-r0), CVE-2026-56407/-56408/-56131
# (libexpat < 2.8.2-r0) — Trivy-Gate scannt HIGH/CRITICAL mit exit-code 1.
#
# Resilienz: GitHub-Runner-Netzwerk liefert zu dl-cdn.alpinelinux.org gelegentlich
# persistente I/O-Errors (APKINDEX fetch exit 99 "stale/unavailable repositories"),
# die jeden E2E-Smoke-Job reißen. Erst retry-basiert (3× mit Backoff), bei
# anhaltendem Ausfall Fallback auf den sekundären dl-4-Mirror — ein CDN-Edge-Ausfall
# darf den Build (und damit pull_request-getriggerte E2E-Smokes) nicht blockieren.
RUN for i in 1 2 3; do \
      apk upgrade --no-cache && break; \
      echo "apk upgrade attempt $i failed, retrying in 5s…"; sleep 5; \
    done || \
    (sed -i 's#dl-cdn.alpinelinux.org#dl-4.alpinelinux.org#g' /etc/apk/repositories && \
     apk upgrade --no-cache)
COPY deploy/nginx/agora.conf /etc/nginx/conf.d/default.conf
COPY --from=frontend-build /app/frontend/dist /usr/share/nginx/html

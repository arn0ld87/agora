# Arbeitsprotokoll · README-Überarbeitung + Versions-Bump 0.9.1-dev (2026-05-05)

**Slice:** Doku-Iteration parallel zum Sub-Slice-29-Backend
**Auslöser:** User-Anfrage nach (a) sichtbarem Beleg für Sub-Slice 29, (b) README-Refresh mit Container-Rebuild-Block, neuer Versions-Aussage, raus aus „Offline-first"-Framing, einladendere Tonalität, neue Bilder/Video.

## Was geändert wurde

### Versions-Bump

| Datei | Vorher | Nachher |
|---|---|---|
| `backend/pyproject.toml` | `0.9.0` | `0.9.1-dev` |
| `frontend/package.json` | `0.9.0` | `0.9.1-dev` |
| `package.json` (Root) | `0.9.0` | `0.9.1-dev` |

Begründung: Tag `v0.9.0` vom 2026-05-01 ist seitdem durch ~30 Commits überholt (Layer 6 TS-Migration komplett, Layer 7 vollständig, Layer 8 Backend, CI-Coverage-Gates, Performance-Iterationen, Stabilitäts-Fixes). `0.9.1-dev` macht für Externen sichtbar, dass `main` post-tag-Iteration trägt; Tag selbst bleibt `v0.9.0`, wird beim nächsten echten Release auf `v0.9.1` oder `v0.10.0` gehoben.

### README-Rewrite

**Raus:**
- Hero-Tagline „Local-first, cloud-kompatibler Persona-basierter Resonanz-Simulator" — irreführend, weil Cloud-LLMs (`qwen3-coder-next:cloud`) der aktuell getestete Default-Pfad sind.
- Dichter Engineering-Stand-Block mit 30+ Bullet-Items, der mehr Implementations-Detail als Use-Case-Wert lieferte.
- Inline-Status-Block „Layer 0–5" — veraltet, jetzt Layer 0–10 mit teilweise Layer 8.

**Rein:**
- Hero-Tagline use-case-orientiert: „Wie reagieren Stakeholder auf dein Dokument? — Frag 132 Personas, bevor du es veröffentlichst."
- Status-Block mit aktueller Versionsaussage `0.9.1-dev` und Verweis auf STATUS.md statt inline-Zahlen.
- Neuer Abschnitt **„Was ist neu seit dem letzten README-Update (2026-05-04)"** mit acht User-sichtbaren Highlights, sortiert nach Impact (Compare-Stack → Runs Dashboard → Persona-Entity-Context → CI-Hardening → Performance → Stabilität → Auth-ADR → Refactoring).
- Workflow-Block mit zwei Inline-Bildern (Graph-Build-Video als GIF + MP4-Klick-Link, Persona-Step-Screenshot).
- Neuer Abschnitt **„Nach größeren Umbauten den Container neu bauen"** mit dem User-bereitgestellten Befehlsblock (`down --remove-orphans` → `build --no-cache agora` → `up -d --force-recreate --remove-orphans` → `ps`). Erklärung dass Named Volumes erhalten bleiben.
- Layer-Tabelle 0–10 mit aktuellem Stand statt 0–5-Aufzählung.
- Footer mit Maintainer-Brand-Link auf [alexle135.de](https://alexle135.de) und Brand-Logo (Platzhalter `media/credits/alexle135-brand.png`).

**Englischer Teil parallel angepasst,** strukturell gleich, etwas knapper.

### Video-Komprimierung

Ausgangs-Datei: `errors/Bildschirmaufnahme 2026-05-04 um 00.37.32.mov` — 1920×950, 22.35 s, 60 fps, H.264, **36 MB**, 12.8 Mbit/s.

Output via ffmpeg:

| Datei | Format | Auflösung | FPS | Bitrate | Größe |
|---|---|---|---|---|---|
| `media/screenshots/graph-build.mp4` | H.264 / MP4 | 1280×632 | 30 | 270 kbps | **747 KB** |
| `media/screenshots/graph-build.gif` | GIF (palette-optimiert) | 800×395 | 10 | — | **5.6 MB** |

50× kleiner für MP4, GIF unter GitHub-Inline-Render-Limit (10 MB).

ffmpeg-Kommandos:

```bash
# MP4 (CRF 24, fast preset, no audio, faststart-flag für Web)
ffmpeg -y -i input.mov \
  -vf "scale='min(1280,iw)':-2,fps=30" \
  -c:v libx264 -preset fast -crf 24 \
  -pix_fmt yuv420p -movflags +faststart -an \
  graph-build.mp4

# GIF (2-Pass mit Palette-Generation für gute Qualität bei kleiner Größe)
ffmpeg -y -i input.mov \
  -vf "fps=10,scale=800:-2:flags=lanczos,palettegen=stats_mode=diff:max_colors=128" \
  /tmp/palette.png

ffmpeg -y -i input.mov -i /tmp/palette.png \
  -lavfi "fps=10,scale=800:-2:flags=lanczos[x];[x][1:v]paletteuse=dither=bayer:bayer_scale=5" \
  graph-build.gif
```

### Bilder-Status (User-Hand-Off)

Drei Bild-Pfade sind in der README referenziert, aber noch nicht im Filesystem:

| Pfad | Status | Inhalt laut User-Anhang |
|---|---|---|
| `media/logo.png` | **bestehend, soll überschrieben werden** | neues Agora-Logo (helles Beige, oranger Mittelpunkt, Sterngraph) |
| `media/screenshots/persona-step.png` | **fehlt** | Screenshot Persona-Erzeugung-UI mit LLM-Modellwahl + Live-Counter |
| `media/credits/alexle135-brand.png` | **fehlt** | AlexLE135.de-Brand für Footer |

Die Bilder muss der Maintainer aus dem Chat ablegen, bevor das README im Browser sauber rendert. Bis dahin zeigt GitHub für die fehlenden Pfade einen broken-image-Indikator — bewusst als Sichtbarmachung des Hand-Offs.

## Verifikation

- `git diff --stat HEAD` zeigt erwartete Änderungen (README.md, 3× version-bump-Files, CHANGELOG.md, neue Assets, dieses Arbeitsprotokoll).
- README rendert syntaktisch sauber (markdown-strict, keine offenen Tags).
- Versions-Konsistenz: alle drei Manifeste auf `0.9.1-dev`.
- Video-Embed-Pattern: `<a href="...mp4"><img src="...gif"/></a>` ist GitHub-konform und funktioniert auf README-Hauptseite.

## Phase-2-Hinweise

- Wenn der Maintainer die Bilder ablegt, ist kein neuer Slice nötig — Pfade sind schon korrekt.
- Beim nächsten echten Release-Tag (`v0.9.1` oder `v0.10.0`) das `-dev`-Suffix in den drei Manifesten entfernen (`scripts/release.sh patch` oder `minor`).
- Demo-Teaser-Video (`static/media/agora-teaser.mp4`) ist unverändert — eigener Slice falls auch das aktualisiert werden soll.

## Refs

- Sub-Slice 29 (Refs #69) — Backend-API für Persona-Entity-Kontext, dessen User-Sichtbarkeit in der README erklärt wurde.
- User-Anfrage `prompt-engineering-expert` Slash-Command (2026-05-05).


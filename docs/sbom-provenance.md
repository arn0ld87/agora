# SBOM und Build-Provenance prüfen

**Stand:** 2026-06-10

Seit Issue #633 erzeugt `docker-image.yml` für jeden Workflow-Run SBOM-Artefakte
und für jeden Registry-Push eine kryptographische Build-Provenance-Attestation.

## Was CI erzeugt

| Job | Artefakt | Format | Inhalt |
|---|---|---|---|
| `build-only` | `agora-image-sbom-spdx` | SPDX-JSON | SBOM des lokal gebauten Images (vor Smoke-Gate) |
| `publish` | `agora-ghcr-sbom-spdx` | SPDX-JSON | SBOM des tatsächlich gepushten GHCR-Images |
| `publish` | GHCR-Attestation | Sigstore/Rekor | Build-Provenance (in-registry, via `actions/attest-build-provenance`) |

Aufbewahrung: SBOM-Workflow-Artefakte 90 Tage. Attestations sind dauerhaft im GHCR-Repository gespeichert.

---

## SBOM-Artefakt herunterladen

```bash
# Letzten erfolgreichen Workflow-Run finden
RUN_ID=$(gh run list --workflow docker-image.yml \
  --repo arn0ld87/agora \
  --status success --limit 1 \
  --json databaseId -q '.[0].databaseId')

# SBOM herunterladen
gh run download "$RUN_ID" \
  --repo arn0ld87/agora \
  --name agora-image-sbom-spdx \
  --dir ./sbom
```

Die Datei `sbom/agora-image.spdx.json` enthält alle Packages (Python, npm, system) mit Namen, Version und SPDX-Lizenz-ID.

---

## SBOM mit syft validieren

```bash
# syft installieren (falls nicht vorhanden)
brew install syft    # macOS
# oder: curl -sSfL https://raw.githubusercontent.com/anchore/syft/main/install.sh | sh -s -- -b /usr/local/bin

# SBOM inhaltlich prüfen (Pakete auflisten)
syft convert sbom/agora-image.spdx.json -o table

# SBOM mit grype auf bekannte CVEs prüfen
grype sbom:sbom/agora-image.spdx.json --fail-on high
```

---

## SBOM mit grype scannen

```bash
# grype installieren
brew install grype    # macOS

# Direkt gegen das GHCR-Image scannen (zieht SBOM-Attestation, falls vorhanden)
grype ghcr.io/arn0ld87/agora:latest

# Oder gegen die heruntergeladene SBOM-Datei
grype sbom:sbom/agora-image.spdx.json
```

---

## Build-Provenance verifizieren

Die Provenance-Attestation ist als Referrer im GHCR-Image-Repository gespeichert.
Sie belegt, aus welchem Commit, welchem Workflow-Run und welcher GitHub-Runner-Umgebung
das Image entstammt.

```bash
# gh 2.49+ benötigt
IMAGE=ghcr.io/arn0ld87/agora:latest

# Attestation abrufen und prüfen
gh attestation verify oci://"$IMAGE" \
  --repo arn0ld87/agora

# Erwartete Ausgabe:
# Loaded digest: sha256:<digest>
# Loaded 1 attestation from GitHub API
# ✓ Verification succeeded!
```

Was `gh attestation verify` prüft:
- Die Attestation ist von GitHub Actions signiert (Sigstore-Rootcert).
- Das Zertifikat enthält den korrekten Repository-Namen und den Workflow-Pfad `.github/workflows/docker-image.yml`.
- Der Subject-Digest stimmt mit dem aktuellen Image-Digest überein.

### Tiefergehende Inspektion

```bash
# Vollständige Provenance als JSON ausgeben
gh attestation verify oci://"$IMAGE" \
  --repo arn0ld87/agora \
  --format json | jq '.[] | .statement.predicate'
```

Enthält u. a.:
- `buildDefinition.resolvedDependencies[].uri` — exakter Git-Commit-SHA
- `runDetails.builder.id` — GitHub-Actions-Runner-ID
- `runDetails.metadata.startedOn` — Build-Zeitstempel

---

## Kompatibilität mit bestehenden Trivy-/Audit-Jobs

Die neuen SBOM-Schritte laufen nach dem Trivy-Scan und beeinflussen dessen
Exit-Code nicht. Der Trivy-Job scannt weiterhin gegen `CRITICAL,HIGH` und
beendet den Build bei Funden (mit Ausnahme der `.trivyignore`-Einträge).
Der SBOM-Upload-Step hat `if-no-files-found: error`, sodass ein fehlgeschlagener
syft-Lauf den Job explizit fehlschlagen lässt.

---

## Verwandte Dokumente

- [`docs/ci-egress-allowlist.md`](ci-egress-allowlist.md) — Netzwerk-Endpunkte, die syft/anchore braucht
- [`docs/release-process.md`](release-process.md) — Container-Release-Workflow
- [`docs/dependency-risk-register.md`](dependency-risk-register.md) — Tracked CVEs und Risiken

# Dependency-Triage: camel-oasis / camel-ai / CVE-Knoten

Stand: 2026-05-07, Europe/Berlin

## Ausgangslage

PR [#315](https://github.com/arn0ld87/agora/pull/315) versuchte `camel-ai`
von `0.2.78` auf `0.2.90` zu heben. Die Triage hat den Resolver-Konflikt
reproduziert; anschliessend wurde #315 auf `camel-ai==0.2.78`
zurueckgebaut und am 2026-05-07 nach `main` gemerged.

Der blockierende Knoten ist `camel-oasis==0.2.5`:

- `backend/pyproject.toml` pinnt `camel-oasis==0.2.5` und `camel-ai==0.2.78`.
- `camel-oasis==0.2.5` pinnt transitiv `camel-ai==0.2.78`,
  `pillow==10.3.0`, `pytest==8.2.0`, `unstructured==0.13.7` und
  `sentence-transformers==3.0.0`.
- `sentence-transformers==3.0.0` limitiert `transformers>=4.34.0,<5.0.0`.
- Python 3.14 bleibt separat durch `tiktoken==0.7.0` blockiert:
  `tiktoken 0.7.0` hat Wheels fuer cp38 bis cp312, aber keine cp314-Wheels.

Aktive Baseline mit Hardstop 2026-07-30:

| Issue | Paket | Version | CVE |
|---|---|---:|---|
| #121 | `pillow` | 10.3.0 | CVE-2026-25990 |
| #122 | `pillow` | 10.3.0 | CVE-2026-40192 |
| #296 | `pillow` | 10.3.0 | CVE-2026-42308 |
| #297 | `pillow` | 10.3.0 | CVE-2026-42310 |
| #298 | `pillow` | 10.3.0 | CVE-2026-42311 |
| #123 | `pytest` | 8.2.0 | CVE-2025-71176 |
| #124 | `transformers` | 4.57.6 | CVE-2026-1839 |
| #125 | `unstructured` | 0.13.7 | CVE-2024-46455 |
| #126 | `unstructured` | 0.13.7 | CVE-2025-64712 |

## Gelesene Quellen

- `AGENTS.md`
- `docs/status.md`
- `docs/dependency-risk-register.md`
- `.github/workflows/ci.yml`
- `backend/pyproject.toml`
- `backend/uv.lock`
- GitHub PRs/Issue per `gh`: #315, #323, #326, #199
- `code-review-graph`: Graph vorhanden, 4639 Nodes, Stand
  `2026-05-06T21:40:02`; Impact-Radius fuer reine Dependency-/Doku-Dateien:
  `low`, 0 Code-Nodes.

## Befehle und Resolver-Ergebnisse

### 1. Baseline-Abhaengigkeitsbaum

```bash
cd backend
uv tree --package camel-oasis
uv tree --invert --package pillow
uv tree --invert --package pytest
uv tree --invert --package unstructured
uv tree --invert --package transformers
uv tree --invert --package sentence-transformers
```

Ergebnis:

- `pillow==10.3.0` haengt an Agora direkt, `camel-ai`, `camel-oasis` und
  `sentence-transformers`.
- `pytest==8.2.0` wird durch `camel-oasis==0.2.5` fixiert.
- `unstructured==0.13.7` wird durch `camel-oasis==0.2.5` fixiert.
- `sentence-transformers==3.0.0` wird durch `camel-oasis==0.2.5` fixiert.
- `transformers==4.57.6` kommt ueber `sentence-transformers==3.0.0`.

### 2. PR #315 lokal reproduziert

Temporare Kopie, nur `camel-ai==0.2.90` simuliert:

```bash
tmpdir=$(mktemp -d /tmp/agora-pr315-repro.XXXXXX)
rsync -a --exclude .venv backend/ "$tmpdir/backend/"
perl -0pi -e 's/"camel-ai==0\.2\.78"/"camel-ai==0.2.90"/' \
  "$tmpdir/backend/pyproject.toml"
cd "$tmpdir/backend"
uv sync --group dev
```

Resolver-Ergebnis:

```text
Because camel-oasis==0.2.5 depends on camel-ai==0.2.78 and your project
depends on camel-ai==0.2.90, we can conclude that your project and
camel-oasis==0.2.5 are incompatible.
```

Bewertung: #315 war als Einzel-Upgrade nicht reparierbar, solange Agora
`camel-oasis==0.2.5` behaelt. Der PR wurde deshalb auf `camel-ai==0.2.78`
zurueckgebaut.

### 3. Gemeinsamer camel-oasis/camel-ai-Upgrade-Dry-Run

Temporare Kopie, `camel-oasis>=0.2.5` plus `camel-ai==0.2.90`:

```bash
tmpdir=$(mktemp -d /tmp/agora-common-camel.XXXXXX)
rsync -a --exclude .venv backend/ "$tmpdir/backend/"
perl -0pi -e 's/"camel-oasis==0\.2\.5"/"camel-oasis>=0.2.5"/; s/"camel-ai==0\.2\.78"/"camel-ai==0.2.90"/' \
  "$tmpdir/backend/pyproject.toml"
cd "$tmpdir/backend"
uv lock --dry-run --upgrade-package camel-oasis --upgrade-package camel-ai==0.2.90
```

Resolver-Ergebnis:

```text
Because only camel-oasis<=0.2.5 is available and camel-oasis==0.2.5
depends on camel-ai==0.2.78, we can conclude that camel-oasis>=0.2.5
depends on camel-ai==0.2.78.
```

Bewertung: Ein gemeinsames Upstream-Upgrade ist aktuell nicht moeglich, weil
kein neueres `camel-oasis` verfuegbar ist.

### 4. Einzelne Upgrade-Pfade

Ungezwungene Dry-Runs:

```bash
cd backend
uv lock --dry-run --upgrade-package pillow
uv lock --dry-run --upgrade-package unstructured
uv lock --dry-run --upgrade-package pytest
uv lock --dry-run --upgrade-package transformers
uv lock --dry-run --upgrade-package sentence-transformers
```

Ergebnis fuer alle: `No lockfile changes detected`.

Erzwungene Fix-Versionen:

| Paket | getestete Fix-Version | Resolver-Ergebnis | Blocker |
|---|---:|---|---|
| `pillow` | 12.2.0 | unloesbar | `camel-ai==0.2.78` erlaubt nur `<11.0.0`; `camel-oasis==0.2.5` pinnt zusaetzlich `pillow==10.3.0` |
| `pillow` | 10.4.0 | unloesbar | `camel-oasis==0.2.5` pinnt `pillow==10.3.0` |
| `pytest` | 9.0.3 | unloesbar | `camel-oasis==0.2.5` pinnt `pytest==8.2.0` |
| `unstructured` | 0.18.32 | unloesbar | `camel-oasis==0.2.5` pinnt `unstructured==0.13.7` |
| `sentence-transformers` | 5.4.1 | unloesbar | `camel-oasis==0.2.5` pinnt `sentence-transformers==3.0.0` |
| `transformers` | 5.8.0 | unloesbar | `sentence-transformers==3.0.0` limitiert `transformers<5.0.0` |

Kontrolltest ohne `camel-oasis`, aber mit `camel-ai==0.2.90`:

```bash
tmpdir=$(mktemp -d /tmp/agora-without-oasis-camel90.XXXXXX)
rsync -a --exclude .venv backend/ "$tmpdir/backend/"
perl -0pi -e 's/    "camel-oasis==0\.2\.5",\n//; s/"camel-ai==0\.2\.78"/"camel-ai==0.2.90"/' \
  "$tmpdir/backend/pyproject.toml"
cd "$tmpdir/backend"
uv lock --dry-run --upgrade-package camel-ai==0.2.90
```

Ergebnis: loesbar; `camel-ai` geht auf `0.2.90`, aber `camel-oasis` und die
OASIS-Transitiven werden entfernt. Das ist technisch ein Dependency-Ausweg,
funktional aber ein OASIS-Replacement-/Decoupling-Slice, kein P0-Patch.

### 5. Audit-Evidenz

Export:

```bash
cd backend
uv export --frozen --no-dev --no-hashes --no-emit-project \
  --format requirements.txt \
  --output-file /tmp/agora-backend-requirements.txt
```

Der vorgeschriebene lokale Aufruf
`uvx pip-audit --strict -r /tmp/agora-backend-requirements.txt || true`
brach auf diesem macOS-Host vor der Advisory-Auswertung bei `ensurepip` mit
`SIGABRT` ab. Mit explizitem Python 3.11 lief dieselbe Requirements-Datei
durch:

```bash
uvx --python /opt/homebrew/bin/python3.11 pip-audit --strict \
  -r /tmp/agora-backend-requirements.txt || true
```

Ergebnis:

```text
Found 9 known vulnerabilities in 4 packages
pillow       10.3.0  CVE-2026-25990  12.1.1
pillow       10.3.0  CVE-2026-40192  12.2.0
pillow       10.3.0  CVE-2026-42308  12.2.0
pillow       10.3.0  CVE-2026-42310  12.2.0
pillow       10.3.0  CVE-2026-42311  12.2.0
pytest       8.2.0   CVE-2025-71176  9.0.3
transformers 4.57.6  CVE-2026-1839   5.0.0rc3
unstructured 0.13.7  CVE-2024-46455  0.14.3
unstructured 0.13.7  CVE-2025-64712  0.18.18
```

### 6. Python 3.14 / tiktoken

```bash
python -m pip index versions tiktoken
curl -fsSL https://pypi.org/pypi/tiktoken/0.7.0/json \
  | jq -r '.urls[] | select(.packagetype=="bdist_wheel") | .filename'
uv lock --dry-run --python 3.14
```

Ergebnis:

- `tiktoken` latest ist `0.12.0`, aber Agora bleibt ueber `camel-ai==0.2.78`
  bei `tiktoken==0.7.0`.
- `tiktoken==0.7.0` hat keine cp314-Wheels.
- `uv lock --dry-run --python 3.14` bleibt gruen, weil Locking keine
  Wheel-Buildbarkeit garantiert. Der Blocker liegt im Install-/Image-Build.

## Entscheidungsmatrix

| Option | Wirkung | CVE-Abbau | Aufwand | Risiko | Empfehlung |
|---|---|---:|---:|---:|---|
| A: #315 als `camel-ai==0.2.90` mergen | hebt nur `camel-ai` | 0 | niedrig | hoch, Resolver rot | Ablehnen; umgesetzt wurde nur der Rollback |
| B: gemeinsames `camel-oasis` + `camel-ai` Upgrade | waere ideal | potenziell hoch | niedrig | aktuell nicht moeglich | Watch, kein Merge |
| C: Einzel-Upgrades `pillow`/`pytest`/`unstructured`/`sentence-transformers`/`transformers` | gezielte CVE-Fixes | theoretisch hoch | niedrig | aktuell unloesbar | Nicht weiter verfolgen, solange `camel-oasis==0.2.5` bleibt |
| D: `camel-oasis` soft-fork mit gelockerten Pins | behebt Knoten direkt | hoch, wenn Tests gruen | mittel | Maintenance-Last, OASIS-Kompatibilitaet | P0-Fallback vorbereiten |
| E: OASIS-Adapter entkoppeln/ersetzen | entfernt Knoten | hoch | hoch | Feature-/Simulationsregression | P1/P0-Eskalation vor Hardstop |
| F: Risikoakzeptanz verlaengern | keine Code-Aenderung | 0 | niedrig | Security-/Compliance-Schuld | Nur mit Sign-off und neuer Frist |

## Empfehlung

1. #315 nicht als `camel-ai==0.2.90`-Upgrade mergen. Der PR war
   resolver-seitig falsch zugeschnitten, weil `camel-oasis==0.2.5` hart
   `camel-ai==0.2.78` verlangt.
2. Dependabot fuer `camel-ai` ignorieren oder nur manuell reaktivieren, bis ein
   neues `camel-oasis` verfuegbar ist.
3. Woechentlich `camel-oasis` Releases pruefen. Sobald `camel-oasis>0.2.5`
   existiert, zuerst gemeinsamen Dry-Run fahren:

```bash
cd backend
uv lock --dry-run --upgrade-package camel-oasis --upgrade-package camel-ai
```

4. Parallel bis spaetestens 2026-06-15 einen Soft-Fork-/Replacement-Slice
   vorbereiten, damit der Hardstop 2026-07-30 nicht von upstream abhaengt.
5. Keine neuen `--ignore-vuln`-Eintraege anfassen. Die aktuelle Baseline bleibt
   korrekt und vollstaendig durch Issues, Owner, Frist und Hardstop gedeckt.

## CVE-Bewertung

| CVE | Reines Dependency-Upgrade heute loesbar? | Grund |
|---|---|---|
| CVE-2026-25990 | Nein | Fix braucht `pillow>=12.1.1`; `camel-oasis` pinnt `10.3.0`, `camel-ai` limitiert `<11` |
| CVE-2026-40192 | Nein | Fix braucht `pillow>=12.2.0`; gleiche Blocker |
| CVE-2026-42308 | Nein | Fix braucht `pillow>=12.2.0`; gleiche Blocker |
| CVE-2026-42310 | Nein | Fix braucht `pillow>=12.2.0`; gleiche Blocker |
| CVE-2026-42311 | Nein | Fix braucht `pillow>=12.2.0`; gleiche Blocker |
| CVE-2025-71176 | Nein | Fix braucht `pytest>=9.0.3`; `camel-oasis` pinnt `8.2.0` |
| CVE-2026-1839 | Nein | Fix braucht `transformers>=5.0.0rc3`; `sentence-transformers==3.0.0` limitiert `<5`, und `camel-oasis` pinnt `sentence-transformers==3.0.0` |
| CVE-2024-46455 | Nein | Fix braucht `unstructured>=0.14.3`; `camel-oasis` pinnt `0.13.7` |
| CVE-2025-64712 | Nein | Fix braucht `unstructured>=0.18.18`; `camel-oasis` pinnt `0.13.7` |

Alle neun CVEs bleiben upstream-blockiert, solange Agora `camel-oasis==0.2.5`
als Runtime-Abhaengigkeit behaelt.

## #323 und #326

- #323 `mistune 3.1.4 -> 3.2.1`: Low-Risk-Update. PR ist offen,
  mergeable und alle sichtbaren Gates waren am 2026-05-07 gruen. Nach Rebase
  erneut CI abwarten, dann bevorzugt vor den P0-Camel-Slices mergen.
- #326 `pygments 2.19.2 -> 2.20.0`: Low-Risk-Update. PR ist offen,
  mergeable und alle sichtbaren Gates waren am 2026-05-07 gruen. Nach Rebase
  erneut CI abwarten, dann ebenfalls mergen.

Diese beiden PRs sind nicht Teil des `camel-oasis`-Knotens und sollten nicht
mit #315 gebundelt werden.

## Risiken

- Upstream koennte bis zum Hardstop kein neues `camel-oasis` releasen.
- Ein Soft-Fork kann OASIS-Laufzeitverhalten veraendern, obwohl der Resolver
  gruen wird.
- `pillow>=12` kollidiert nicht nur mit `camel-oasis`, sondern auch mit dem
  aktuellen `camel-ai<11`-Constraint.
- `pytest>=9` kann lokale Test-/Plugin-Kompatibilitaet brechen; das ist erst
  nach Entfernen des `camel-oasis`-Pins sinnvoll testbar.
- `transformers>=5` ist ein groesserer ML-Stack-Sprung; `sentence-transformers`
  muss gemeinsam getestet werden.
- Python 3.14 bleibt ein Build-Thema, selbst wenn `uv lock --python 3.14`
  erfolgreich ist.

## Definition of Done fuer die naechste P0-Umsetzung

1. Gewaehlte Option ist als Issue/PR dokumentiert, inklusive Owner und Frist.
2. `uv lock --dry-run` zeigt einen loesbaren Plan fuer den gewaehlten Pfad.
3. `uv sync --group dev` laeuft lokal und in CI gruen.
4. Contract-Tests, Ruff und Mypy laufen gruen:

```bash
cd backend && uv run pytest tests/contracts/ -v
cd backend && uv run ruff check .
cd backend && uv run mypy app
```

5. `pip-audit --strict` zeigt keine neuen Findings und reduziert mindestens
   einen Baseline-Eintrag, oder die Baseline bleibt unveraendert mit
   dokumentiertem Upstream-Blocker.
6. Keine neuen `--ignore-vuln`-Eintraege ohne Issue, Owner, Deadline und
   Hardstop.
7. OASIS-Smoke laeuft fuer mindestens einen minimalen Simulationspfad, falls
   `camel-oasis`, `camel-ai`, `sentence-transformers` oder `transformers`
   tatsaechlich geaendert werden.

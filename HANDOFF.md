# Handoff — Agora 0.10.0-RC Implementation

**Stand:** 2026-09-24
**Basis:** `main` nach PR #1547 (f005 Decision-Layer, gemergt)
**Ersetzt:** die Version dieser Datei vom 2026-09-20 (Stand `main @ b62aea62`) — siehe „Verhältnis zum alten Plan" unten, bevor du dort weiterarbeitest.

---

## Wo die Arbeit tatsächlich läuft: PandaOS Tracked Work `f006`

Diese Session hat die 0.10.0-Arbeit nicht über `docs/plans/active/0.10.0-rc-plan.md` fortgeführt, sondern über PandaOS Tracked Work (Feature-ID **`f006`**, Titel „Agora 0.10.0: die neun Release-Prioritäten", Scale `epic`, 8 Slices). Wenn du in einer PandaOS-Session mit Zugriff auf `work_read`/`work_slice`/`work_task` bist:

```
work_read                     # zeigt f006 mit allen Slices, Status, offenen Gates
```

Wenn du **keinen** PandaOS-Zugriff hast (reines Git/Terminal), ist der Plan-Inhalt trotzdem hier vollständig rekonstruierbar — siehe unten.

### Erledigt (gemergt bzw. als offener PR)

| Slice | Issue(s) | PR | Branch | Inhalt |
|---|---|---|---|---|
| `embedding-ssot` | #1417 (Slice 2.3/2.4) | **#1548**, offen, CI grün | `feat/f006-embedding-ssot` | `resolve_operational_vector_dim()` (VECTOR_DIM aus aktiver Indexversion statt `.env`), `/readyz`-Check `embedding_index_version` gegen echte Neo4j-Realität, `GET /api/llm/embedding/index-versions` + Frontend-UI für Betriebsindex/`building`-Status |
| `sim-fidelity` | #1236 | **#1549**, offen, CI grün | `feat/f006-sim-fidelity` | `install_recsys_mean_pooling_patch()` — Twitter-Recommender rankt jetzt über Mean-Pooling statt zufallsinitialisiertem `pooler_output`. Zwei Commits: Hauptfix + ein Codex-Review-Fix (fp16-dtype-Erhalt der Maske) |

Beide PRs sind vollständig CI-grün (inkl. Backend/Frontend-Smoke-Gates, Playwright, CodeQL). **Merge-Reihenfolge:** unabhängig voneinander, keine Abhängigkeit zwischen den beiden Branches — beide direkt gegen `main` mergebar, Reihenfolge egal. Empfohlene Merge-Strategie: **Squash** (beide PRs sind atomare Slices mit Fixup-Commits, die keinen eigenständigen Wert haben).

### Blockiert — bewusst nicht angefasst

Die restlichen vier Slices (`job-queue`, `entity-resolution`, `evidence-trust`, `repro-manifest`) sind **alle** aktuell nicht agentenfähig. Vor jedem Claim wurde das zugehörige GitHub-Issue-Label geprüft (`gh issue view <n>`):

| Slice | Blockiert durch | Label/Grund |
|---|---|---|
| `job-queue` | Plan-Gate `queue-architecture` | Architekturentscheidung (RQ/Redis vs. eigener Worker-Prozess vs. Serialisierung über #1526) explizit dem Nutzer vorbehalten, kein GitHub-Issue |
| `entity-resolution` | #1470 | `ready-for-human` — Identitätsmodell-/Ontologie-Entscheidung, Maintainer-Begründung: „ein falscher Merge ist schwer rückgängig zu machen" |
| `evidence-trust` | #1345, #1240, #1400 | alle `ready-for-human`. #1301 (Vorstufe) ist bereits `CLOSED`/erledigt |
| `repro-manifest` | #763 (Parent), #1274 | #763 ist `CLOSED` mit Label `wontfix` — Maintainer hat das Ur-Vorhaben abgelehnt. #1274 trägt `ready-for-human` |

**Muster, das sich wiederholt:** Jedes Issue, das Ontologie-, Identitäts-, Gate-Semantik- oder Architekturfragen berührt, ist in diesem Repo bewusst auf `ready-for-human` gesetzt. **Prüfe das Label über `gh issue view <n>`, bevor du eine dieser vier Slices bearbeitest** — sonst baust du an einer Entscheidung vorbei, die der Maintainer sich ausdrücklich vorbehalten hat.

Innerhalb von `sim-fidelity` wurden aus demselben Grund zwei Tasks deferred, nicht bearbeitet: `leakage-messung`/`leakage-grenze` (#1323, `ready-for-human`). Das Slice-Akzeptanzkriterium („Role Leakage gemessen und unter der Grenze") ist damit **nur zur Hälfte erfüllt** — der Recommender-Teil ist fertig, der Leakage-Teil bleibt offen.

Diese Entscheidungen sind in `f006` als Plan-Notizen festgehalten (`alle-verbleibenden-slices-blockiert`, `vector-dim-bootstrap-bleibt-env`, `recommender-ehrlich`). Mit PandaOS-Zugriff: in der Progress-Ansicht der Feature sichtbar. Ohne: siehe „Backlog-Punkte" unten.

### Nächster sinnvoller Schritt

Es gibt **keine** weitere Slice, die ohne eine der oben genannten Entscheidungen bearbeitbar wäre. Der nächste Schritt ist eine der fünf offenen Entscheidungen (Architektur-Wahl `queue-architecture`, oder eine der vier `ready-for-human`-Issues in Domänenregeln übersetzen und auf `ready-for-agent` umlabeln) — nicht weiterer Code.

---

## Verhältnis zum alten Plan (`docs/plans/active/0.10.0-rc-plan.md`)

Diese Datei existiert weiterhin (36 KB, zuletzt geändert 2026-09-20) und beschreibt einen **eigenen, separaten Wellenplan** (Slices 1.1–4.3) für dieselbe ROADMAP-P0-Priorität. Sie ist **nicht aktuell gehalten worden**: `git log` zeigt Slice 1.4 (#1472c, Commit `908354a9b`) und Slice 4.1 (#1471, Commit `8b3cfbf95`) bereits auf `main` gemergt, aber die Tabelle in dieser Datei führt sie nicht als erledigt.

**Vor jeder Arbeit an dieser Datei:** prüfen, ob die dort geplanten Slices 2.3 (VECTOR_DIM-SSoT) und 4.2/4.3 (Entity Resolution/Entitätsklassen) nicht bereits durch `f006/embedding-ssot` (2.3, siehe oben) bzw. durch die `entity-resolution`-Blockade (4.2/4.3 = #1470) abgedeckt bzw. bewusst blockiert sind. Zwei parallele Pläne für dieselbe Arbeit sind ein Risiko für Doppelarbeit — `docs/STATUS.md` ist im Zweifel die verlässlichere Quelle für den Istzustand als eine der beiden Planungsdateien.

---

## Backlog-Punkte aus dieser Session (ohne PandaOS-Zugriff nicht anders sichtbar)

- **`hf-token-unauthenticated-download`**: `Twitter/twhin-bert-base` (1,06 GB) wird bei jedem Simulationsstart unauthentifiziert von Hugging Face geladen — für eine „lokal betreibbare" Plattform eine unbeabsichtigte externe Abhängigkeit im Startpfad, ratelimitiert ohne `HF_TOKEN`. Nebenbefund aus #1236, nicht Teil von dessen Akzeptanzkriterien.
- **`show-index-query-dupliziert`**: Die `SHOW INDEXES`-Cypher-Query existiert wortgleich in `Neo4jStorage.index_state()` und `Neo4jReEmbedder.index_is_online()` (bewusst dokumentierte Duplikation wegen unterschiedlicher Driver-Lebensdauer) — bei der nächsten Änderung an dieser Query beide Stellen synchron halten.
- **`modellwechsel-e2e-nachweis`**: Ein tatsächlich durchgeführter Embedding-Modellwechsel gegen echtes Neo4j und echtes Embedding-Backend steht als Nachweis noch aus (in dieser Session nicht durchführbar, kein Neo4j lokal verfügbar).

---

## Arbeitsumgebung (unverändert gegenüber der alten Handoff-Version)

**Backend-Tests laufen lokal auf dem Mac**, mit zwei Einschränkungen:
- Modelle, die Netzwerk brauchen (z. B. `Twitter/twhin-bert-base`), sind mit `@pytest.mark.llm` markiert und laufen **nicht** im Default-Lauf (`addopts` in `backend/pyproject.toml` schließt `llm` und `integration` aus). Explizit: `pytest -m llm`.
- Auf macOS bricht `torch`/`transformers` mit `OMP: Error #15` ab, wenn mehrere OpenMP-Runtimes geladen werden. Workaround, der in dieser Session zuverlässig funktionierte: `KMP_DUPLICATE_LIB_OK=TRUE uv run pytest ...` voranstellen.
- Neo4j/Redis sind lokal nicht verfügbar — `tests/integration/` bleibt ausgeschlossen (`-m 'not integration'`, Default).

**Frontend** läuft lokal (`bun run test`, `bun run check`).

**Branch-Hygiene:** Diese Session hat wiederholt festgestellt, dass alte, bereits gemergte Feature-Branches (z. B. `fix/agents-md-pandaos-leak`, dessen PR #1546 längst gemergt war) als Ausgangspunkt für neue Arbeit missbraucht wurden — mit der Folge, dass neue Commits auf einem Branch landeten, der selbst hinter `main` zurücklag. **Vor dem ersten Commit einer neuen Slice:** `git fetch origin && git checkout -b feat/f006-<slice-name> origin/main` — nie auf einem Branch weiterarbeiten, dessen eigener PR schon gemergt ist (`gh pr list --head <branch>` prüfen).

---

## Gates

```bash
# Backend
cd backend && uv run pytest tests/contracts/ -x -q \
  && uv run python -m app.contracts.dump_schemas --check \
  && uv run ruff check . && uv run mypy app

# zusätzlich bei Aenderungen an backend/scripts/:
uv run python scripts/check_mypy_debt.py
uv run python scripts/check_complexity.py

# Frontend
cd frontend && bun run test && bun run check
```

`Backend PR smoke gate` in CI läuft mit `-x` (bricht beim ersten Fehler ab) — bei Änderungen mit globaler Wirkung lohnt sich ein lokaler Lauf ohne `-x`, sonst tauchen Folgefehler erst über mehrere CI-Runden auf.

---

## Was in dieser Session gelernt wurde

**Ein Sonnet-Reviewer pro Slice reicht** (Kostenregel — kein Doppel-Review). Beide Slices in dieser Session wurden mit genau einem Reviewer-Durchgang (alle Achsen in einem Prompt) plus eigener Mutationsprobe verifiziert, keine Opus-Eskalation nötig.

**Mutationsproben sind billig und beweisen, dass ein Test tragend ist.** Für beide Slices wurde der jeweilige Fix testweise zurückgesetzt, um zu zeigen, dass die neuen Tests wirklich rot werden — nicht nur grün laufen, weil sie nichts prüfen. Muster: Datei sichern (`cp x.py /tmp/x_backup.py`), Fix zurücksetzen, Test laufen lassen, Original wiederherstellen, `git diff --stat` prüfen (muss leer/unverändert sein).

**„Identische Ergebnisse bei gleichem Seed" ist ein schwächeres Kriterium, als es klingt.** Beim Twitter-Recommender-Fix (#1236) zeigte sich: Der ungepatchte, kaputte Pfad lieferte *auch* deterministische Ergebnisse — nur degenerierte (alle Nutzer bekommen denselben Feed). Ein reiner Determinismus-Test hätte den Bug nicht gefangen. Der harte Diskriminator war die Personalisierung. Bei jedem „gleicher Seed → gleiches Ergebnis"-Akzeptanzkriterium prüfen, ob das Ergebnis dabei auch *korrekt* ist, nicht nur stabil.

**Codex-Reviews auf offenen PRs lohnen sich zu lesen, bevor man den Nutzer fragt, was zu tun ist.** PR #1549 bekam einen echten P2-Fund (fp16-Maske wurde hart auf fp32 gecastet, hätte den Zweck des bestehenden Speicherprofils für Kleincontainer unterlaufen) — per `gh api repos/<owner>/<repo>/pulls/<n>/comments` abrufbar, nicht in der normalen `gh pr view --comments`-Ausgabe sichtbar.

---

## Kontakt

- Repo: https://github.com/arn0ld87/agora
- Istzustand: [`docs/STATUS.md`](docs/STATUS.md)
- Release-Reihenfolge: [`ROADMAP.md`](ROADMAP.md)
- Offene PRs aus dieser Session: [#1548](https://github.com/arn0ld87/agora/pull/1548), [#1549](https://github.com/arn0ld87/agora/pull/1549)

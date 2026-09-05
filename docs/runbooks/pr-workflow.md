# PR-Workflow

**Stand:** 18.07.2026

## Kernregel

Jede Änderung geht über einen Pull Request. Direkte Pushes auf `main` sind verboten.

## 1. Issue und Release-Scope prüfen

Vor dem Branch:

- zugehöriges GitHub Issue vollständig lesen
- aktuelle Produktversion aus `VERSION` prüfen
- Release-Gate in `ROADMAP.md` bestätigen
- Scope, Out-of-Scope und Akzeptanzkriterien klären

Ein PR ohne Issue ist nur für kleine administrative Korrekturen zulässig und muss im Body begründen, warum kein eigenes Issue nötig ist.

## 2. Branch anlegen

```bash
git fetch origin
git switch -c <typ>/<kurzbeschreibung> origin/main
```

Erlaubte Präfixe:

- `feat/`
- `fix/`
- `refactor/`
- `docs/`
- `chore/`
- `security/`

## 3. Atomarer Scope

Ein Pull Request behandelt genau eine prüfbare fachliche Einheit. Getrennt bleiben insbesondere:

- Dokumentationsumbau und Laufzeitänderung
- Provider-Erkennung und Frontend-Redesign
- Datenmigration und neues Produktfeature
- E2E-Ursachenbehebung und kosmetische Testlockerung

Persistierte Datenänderungen benötigen Migration, Resume-/Rollback-Überlegung und Tests.

## 4. Quality-Gate vor Push

```bash
# vollständig
bash scripts/pre-push-gate.sh

# gezielt
bash scripts/pre-push-gate.sh backend
bash scripts/pre-push-gate.sh frontend
bash scripts/pre-push-gate.sh schemas
```

Zusätzlich laufen die im Issue genannten gezielten Tests.

Verboten:

- `--no-verify` ohne ausdrückliche Freigabe
- globale Skips
- abgeschwächte Assertions
- pauschale Retries als Ersatz für Ursachenbehebung
- Coverage-Erhöhung durch kleinere Include-Globs

## 5. Commit

```bash
git add <konkrete-dateien>
git commit -m "<typ>(<scope>): <beschreibung> (Refs #<NR>)"
```

Keine pauschalen `git add .`-Commits bei gemischtem Workspace.

## 6. Pull Request erstellen

```bash
git push -u origin <branch>
gh pr create --base main --head <branch>
```

Der PR-Body enthält:

```markdown
## Summary
- Was wurde geändert?

## Release-Ziel
- Welche Version und welches Gate betrifft der PR?

## Scope
- Welche Dateien, Verträge oder Flows gehören dazu?

## Out-of-Scope
- Welche Folgearbeit wurde bewusst ausgelagert?

## Tests
- Exakte Befehle und Ergebnisse

## Migration / Rollback
- Falls persistierte Daten oder Konfiguration betroffen sind

## Tracking
- Closes #<Issue> oder Refs #<Issue>
```

## 7. Review

Vor dem Merge:

- automatisierte Checks grün
- relevante Code-Review-Findings geprüft
- Security-, Datenintegritäts- und Contract-Findings behoben oder begründet ausgelagert
- keine offene HIGH-/P0-Feststellung
- bei Cross-Layer-, Security- oder Migrationsänderungen zusätzliche Lead-Prüfung

Automatisches Review ersetzt keine Prüfung der tatsächlichen Systemgrenzen. Ein Bot mit grünem Häkchen ist kein Architekt, nur ein Bot mit grünem Häkchen.

## 8. Dokumentation synchronisieren

Nur die zuständige Quelle ändern:

- tatsächlicher Istzustand → `docs/STATUS.md`
- Release-Gate oder strategische Reihenfolge → `ROADMAP.md`
- ausgeliefertes Verhalten → Fragment `changelog.d/<pr-nr>-<slug>.md` (nie direkt `CHANGELOG.md`; Konvention in `changelog.d/README.md`)
- konkrete Folgearbeit → GitHub Issue
- Architekturentscheidung → ADR
- operativer Ablauf → Runbook

Keine neue parallele Planungsdatei anlegen.

## 9. Merge

Merge erst wenn:

- Scope und Akzeptanz erfüllt sind
- alle verpflichtenden Checks grün sind
- offene Review-Findings geklärt sind
- Dokumentation und Issue-Status stimmen

```bash
gh pr merge --squash
```

### Branch-Protection: offene Review-Threads blockieren den Merge

Seit 24.08.2026 ist auf `main` `required_conversation_resolution` aktiv (#1384).
Ein **ungelöster Review-Thread blockiert den Merge technisch**, nicht nur sozial —
der Merge-Button ist nicht klickbar, solange ein Thread offen ist.

Anlass: PR #1380 wurde mit drei vom Review korrekt erkannten, unbehobenen
Fehlern gemergt. Die CI war vollständig grün; die 17 Statusprüfungen griffen,
der Review-Befund griff nicht.

```bash
# Ist-Zustand pruefen
gh api repos/arn0ld87/agora/branches/main/protection \
  -q '.required_conversation_resolution.enabled'   # -> true

# Offene Threads eines PR zaehlen (CI-gruen heisst nicht thread-frei!)
gh api graphql -f query='
{ repository(owner:"arn0ld87", name:"agora") {
    pullRequest(number:<N>) {
      reviewThreads(first:50) { nodes { isResolved } } } } }' \
  -q '[.data.repository.pullRequest.reviewThreads.nodes[]
       | select(.isResolved==false)] | length'
```

Ein Thread wird über „Resolve conversation" geschlossen. Das ist eine bewusste
Handlung: entweder ist der Befund behoben, oder er ist im Thread begründet
zurückgewiesen. Beides ist zulässig, stilles Übergehen nicht mehr.

**`strict` (Branch muss aktuell sein) bleibt bewusst deaktiviert.** Bei mehreren
parallelen PRs würde jeder Merge auf `main` die 17 Checks aller übrigen PRs neu
auslösen. Der Schutz vor semantischen Merge-Konflikten wiegt das bei kleinen,
atomaren Slices nicht auf. Bei größeren Umbauten den PR vor dem Merge manuell
rebasen.

**Dependabot** ist davon nicht dauerhaft betroffen: Dependabot-PRs erhalten in
der Regel keine Review-Threads. Bleibt ein Bot-Thread offen (z. B. von
CodeRabbit), gilt derselbe Weg — auflösen oder begründet zurückweisen.

## 10. Cleanup

```bash
git switch main
git pull --ff-only
git branch -d <branch>
git push origin --delete <branch>
```

## Admin-Override

Ein Merge mit roter CI benötigt:

- explizite Admin-Entscheidung
- dokumentierten Grund
- Risiko und Rollback
- sofortiges Folge-Issue

„Ist nur Doku“ ist keine automatische Ausnahme, wenn Links, Versionen oder Steuerungsquellen geändert werden.

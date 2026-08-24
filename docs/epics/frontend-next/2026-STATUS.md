# Frontend-Next — verifizierter Ist-Stand

**Erstellt:** 2026-07-26
**Anlass:** [Issue #836](https://github.com/arn0ld87/agora/issues/836) — der Ist-Stand des React-/Lovable-Vorhabens musste belegt werden, bevor er an anderer Stelle eingeordnet wird.
**Charakter:** reine Tatsachenfeststellung. Dieses Dokument trifft **keine** Architektur- oder Freigabeentscheidung; die verbindliche Einordnung ist Gegenstand von [Issue #837](https://github.com/arn0ld87/agora/issues/837).

Erhebungsmethode: Lovable-MCP-Connector (nur lesend, keine Aktion am Projekt), `gh`, lokale Git-Historie, Dateisystem, Volltext der acht Dokumente in diesem Verzeichnis.

---

## Kernaussage

`brief.md` trägt in Zeile 3 die Stand-Zeile:

> „Entwurf / Analyse-Ergebnis, noch kein Lovable-Projekt angelegt, keine Umsetzung gestartet.“

Diese Zeile ist **überholt**. Sie beschreibt den Stand am 2026-07-16 vor der Projektanlage und wurde danach nie aktualisiert. Tatsächlich existiert ein Lovable-Projekt mit substanzieller Umsetzung. Es ist jedoch **derzeit nicht veröffentlicht** und **nicht** mit einem produktiven Agora-Deployment verbunden.

Zur Genauigkeit dieser Aussage: Der Connector liefert mit `is_published` einen **Momentanwert**, keine Veröffentlichungshistorie. Belegt ist damit der Zustand zum Erhebungszeitpunkt 2026-07-26. Ob ein Projekt zwischenzeitlich veröffentlicht und später wieder zurückgezogen wurde, lässt sich aus den verfügbaren Feldern nicht ausschließen — siehe „Unklar“.

---

## Belegt

Fakten mit benannter Primärquelle. Die Connector- und `gh`-Zeilen stehen unabhängig von den Handover-Dokumenten; die letzte Zeile ist bewusst ein *Abgleich* zwischen beiden und daher nicht unabhängig.

| Feststellung | Beleg |
|---|---|
| Lovable-Workspace „Alexander's Lovable“ existiert, Plan `pro`, 5 Projekte | Connector `list_workspaces`, Workspace-ID `ywW2AknvnOdwQW1Yt23P` |
| Lovable-Projekt „Agora Runs Dashboard“ existiert | Connector `list_projects`, Projekt-ID `a061f7f7-294f-4380-935d-a8f0eb4110a3` |
| Angelegt 2026-07-16T07:55:21Z, letzte Änderung 2026-07-17T19:59:29Z, Status `completed` | Connector `list_projects` |
| **`is_published: false`** zum Erhebungszeitpunkt, kein `url`-Feld | Connector `list_projects` |
| 23 Edits: 9 Lovable-AI-Commits, 14 lokale Developer-Commits | Connector `list_edits` |
| Codebasis: TanStack-Router-SPA, 12 Routen, 7 API-Module, 7 Contract-Module, shadcn/ui | Connector `list_files` (`src/routes/`, `src/api/`, `src/contracts/`) |
| Zweites Projekt „Agora Prototype“ (`c6e02187-301e-44b5-bddb-d2471befe332`) existiert, hat aber **null Edits** | Connector `list_edits` liefert leeres Array |
| GitHub-Sync-Repo `arn0ld87/agora-runs-dashboard` existiert, **privat** | `gh repo view`, angelegt 2026-07-16T08:32:50Z |
| Letzter Push dorthin 2026-07-17T19:59:31Z — deckt sich sekundengenau mit dem letzten Lovable-Edit | `gh repo view` vs. Connector `list_edits` |
| *Abgleich:* die in `HANDOVER.md` genannte Projekt-ID stimmt mit der Connector-Antwort überein | Primärquelle ist der Connector; `HANDOVER.md` Abschnitt „Lovable-Projekt“ dient nur der Gegenprobe |

Zur Umsetzungstiefe sind zwei Beweisgrade zu trennen:

**Durch `list_files` belegt** — diese Dateien existieren im Projekt: die Routen `onboarding`, `simulation`, `report` (inkl. `report.interaction`), `settings`, `history`, `compare`, `runs` und `runs.$runId`; die API-Module `client`, `compare`, `onboarding`, `report`, `runs`, `settings`, `simulation`; die zugehörigen Contract-Module; `auth/useApiAuth.ts` und `hooks/useSimulationStream.ts`.

**Nur durch Commit-Messages behauptet** — dass diese Flächen fachlich vollständig und korrekt verdrahtet sind. Commit-Nachrichten belegen, dass Änderungen vorgenommen und wie sie gemeint waren, nicht dass das Ergebnis funktioniert. Eine Codeprüfung oder ein Testlauf gegen das Projekt war nicht Gegenstand von #836.

Ebenfalls nur aus Commit-Messages, also mit demselben Vorbehalt, ergeben sich die offenen Enden:

- die Settings-Tabs Routing, Embedding-Migration, API-Keys und Audit-Log zeigen laut Commit `32fdb0dc` einen „nicht angebunden“-Platzhalter,
- es existiert laut Commit `1955fea0` kein Aufrufer, der eine echte `simulation_id` liefert — der Run-Erstellungspfad fehlt.

---

## Lokal

| Feststellung | Beleg |
|---|---|
| `frontend-next/` existiert **nicht** im Agora-Repo-Root | `ls -la frontend-next` → „No such file or directory“ |
| In keinem der 282 lokal vorhandenen Refs wurde je eine Datei unter `frontend-next/` hinzugefügt | `git log --all --diff-filter=A --name-only -- 'frontend-next/*' 'frontend-next'` → leer. Schließt Renames, gekürzte Historie und nie gefetchte Remotes nicht aus |
| Kein Eintrag für `frontend-next` in `.gitignore` | `grep` ohne Treffer |
| Genau zwei **getrackte** `package.json`: `package.json`, `frontend/package.json` | `git ls-files '*package.json'` — ohne Tiefenbegrenzung; alle weiteren Treffer eines rohen `find` liegen in `backend/.venv/` oder `.claude/worktrees/` und sind nicht Teil des Repos |
| Die Branches `feat/frontend-next`, `origin/feat/frontend-next-phase12`, `origin/feat/frontend-next-phase2-onboarding-granularity` enthalten **null** `.tsx`-Dateien | `git ls-tree -r --name-only <branch> \| grep -c '\.tsx$'` → 0 |
| Ein lokaler Klon des React-Projekts liegt **außerhalb** dieses Repos unter `/Volumes/T7/Projekte/agora-runs-dashboard` | `ls`, `git log` |
| Dieser Klon steht auf `32fdb0d` (2026-07-16) und ist damit **hinter** dem Lovable-Stand; zusätzlich uncommittete Änderungen | `git log -1`, `git status --short` |
| Klon enthält 65 `.tsx`-Dateien | `find src -name '*.tsx' \| wc -l` |

Wichtig für das mentale Modell: Die trotz ihres Namens „frontend-next“ heißenden Branches enthalten **Vue**-Arbeit am bestehenden Frontend, keinen React-Code. Der React-Code hat nie im Agora-Repository gelegen.

---

## Lovable

Was der Connector unmittelbar zeigt, ohne Umweg über die Handover-Dokumente:

| Projekt | ID | Edits | Status | Published (Stand 2026-07-26) |
|---|---|---|---|---|
| Agora Runs Dashboard | `a061f7f7-294f-4380-935d-a8f0eb4110a3` | 23 | `completed` | **nein** |
| Agora Prototype | `c6e02187-301e-44b5-bddb-d2471befe332` | 0 | `completed` | **nein** |

„Agora Prototype“ wurde am 2026-07-16T07:15:28Z angelegt und drei Sekunden später zuletzt berührt. Ohne einen einzigen Edit ist es eine leere Projekthülle, kein Umsetzungsstand.

Die drei weiteren Projekte im Workspace („Delightful Designs“, „Grade Overview“, „Dify Chat Studio“) gehören nicht zu Agora.

Zur Preview-URL: Lovable hält für jedes Projekt eine interne Preview-Adresse bereit. Das ist eine Editor-Vorschau, keine Veröffentlichung — `is_published` bleibt davon unberührt und stand bei beiden Agora-Projekten am 2026-07-26 auf `false`.

---

## Planung

Was ausschließlich in Planungs- und Übergabedokumenten steht. Diese Dokumente sind überwiegend **Arbeitsaufträge an nachfolgende Agenten-Sessions**, keine Abnahmeberichte — ihre Fertigstellungsangaben sind Behauptungen, nicht Nachweise.

| Dokument | Typ | Inhalt |
|---|---|---|
| `brief.md` | Konzept | vollständiger Architektur-Brief für die React-SPA; die veraltete Stand-Zeile ist seit Issue #910 korrigiert und verweist für den Ist-Stand auf dieses Dokument |
| `HANDOVER.md` | Übergabe-Prompt | nennt Projekt-ID, Editor-, Preview- und GitHub-Sync-URL; bezeichnet Slices 1–3 als „live in der Preview“ |
| `HANDOVER-GLM-MMX.md` | Übergabe-Prompt | Übergabe Phase 1+2 an eine Folge-Session |
| `PHASE-1-2-OPUS-HANDOVER.md` | Übergabe-Prompt | Kanon-Entscheidung `routing/defaults.global_default` als SSoT |
| `PHASE-1-DIVERGENZ.md` | Analyse | Inventar der konkurrierenden Persistenz-Senken der Modellwahl |
| `PHASE-2-ONBOARDING-HANDOVER.md` | Übergabe-Prompt | hält Phase 2 ausdrücklich als **offen** fest, Design-Konflikt ungeklärt |
| `PHASE-5-VERIFICATION-HANDOVER.md` | Übergabe-Prompt | Verifikationsplan; nennt als Vorbedingung, dass Phase 3+4 ausgeliefert ist |

Der Dateiname `PHASE-5-VERIFICATION-HANDOVER.md` trägt keine Aussage über tatsächlich durchgeführte Verifikation. Das Dokument ist der Auftrag dazu, nicht dessen Ergebnis.

### Fremdkörper im Verzeichnis

`SLICE-5.2-ENVSETUP-KANON-MIGRATION.md` liegt zwar hier, behandelt aber ausschließlich **Vue**-Komponenten (`EnvSetupModelPanel.vue`, `Step2EnvSetup.vue`, `AiModelPicker.vue`) und gehört zu [Issue #890](https://github.com/arn0ld87/agora/issues/890) am bestehenden Produktfrontend. Es ist als einziges Dokument des Verzeichnisses am 2026-07-26 geändert worden, alle übrigen stammen vom 2026-07-18. Es zählt nicht zum React-Vorhaben.

Die Datei trägt seit Issue #910 einen entsprechenden Hinweis im Dokumentkopf. Sie wurde bewusst **nicht** verschoben: auf ihren Pfad verweisen `CHANGELOG.md` (Eintrag zu #890) sowie `PHASE-2-ONBOARDING-HANDOVER.md` an zwei Stellen, und ein CHANGELOG-Eintrag ist Auslieferungshistorie, die nicht nachträglich umgeschrieben wird.

### Irreführende Branch-Benennung

Die Branchnamen `feat/frontend-next`, `origin/feat/frontend-next-phase12` und `origin/feat/frontend-next-phase2-onboarding-granularity` legen React-Arbeit nahe. Tatsächlich enthält keiner der drei eine einzige `.tsx`-Datei.

Der Beleg zählt ausschließlich die Dateiendung `.tsx`. Er schließt damit React-Komponenten in JSX-Syntax aus, **nicht** React-Code in reinen `.ts`-Dateien. Für die praktische Frage „liegt hier eine React-SPA?“ reicht das: eine React-Oberfläche ohne eine einzige `.tsx`-Datei ist unrealistisch. Eine erschöpfende Framework-Inventur der drei Branches ist damit aber nicht erbracht.

Beleg via `git ls-tree -r --name-only <branch> | grep -c '\.tsx$'`, erhoben 2026-07-31:

| Branch | `.tsx`-Dateien |
|---|---|
| `feat/frontend-next` | 0 |
| `origin/feat/frontend-next-phase12` | 0 |
| `origin/feat/frontend-next-phase2-onboarding-granularity` | 0 |

Wer in diesen Branches eine React-SPA sucht, sucht vergeblich. Der React-Code entsteht im Lovable-Projekt und wird ins separate, private Repository `arn0ld87/agora-runs-dashboard` synchronisiert (siehe „Belegt“).

---

## Unklar

Nicht zuverlässig verifizierbar, ohne den Rahmen von #836 zu verlassen:

- Ob die als „live in der Preview“ bezeichneten Slices 1–3 funktional vollständig sind. Belegt ist, dass entsprechender Code existiert und Commits mit passenden Nachrichten gelaufen sind — nicht, dass die Oberfläche fehlerfrei bedienbar ist. Ein Preview-Abruf oder Testlauf war nicht Gegenstand dieses Tickets.
- Der Grad der Divergenz zwischen Lovable-Remote, GitHub-Sync-Repo und lokalem Klon. Belegt ist nur, dass der lokale Klon älter ist und uncommittete Änderungen trägt.
- Ob der lokale Klon `/Volumes/T7/Projekte/agora-runs-dashboard` noch aktiv bearbeitet wird oder liegen geblieben ist.
- Warum „Agora Prototype“ angelegt und sofort aufgegeben wurde.
- Ob eines der Projekte **zwischenzeitlich** veröffentlicht und später zurückgezogen wurde. `is_published` ist ein Momentanwert; der Connector liefert keine Veröffentlichungshistorie, und `list_edits` enthält keine Publish-/Unpublish-Ereignisse. Für den Zeitraum vor dem 2026-07-26 ist dazu keine Aussage belegbar.

---

## Produktiver Status

**Kein React-/Lovable-Frontend ist derzeit produktiv mit Agora verbunden oder veröffentlicht.**

Belege:

- beide Lovable-Projekte tragen zum Erhebungszeitpunkt `is_published: false` und besitzen keine öffentliche URL,
- das GitHub-Sync-Repo `arn0ld87/agora-runs-dashboard` ist privat — für sich genommen **kein** Beweis gegen ein Deployment, denn auch aus privaten Repos lässt sich deployen; hier nur als ergänzender Umstand,
- weder `docker-compose*.yml` noch `deploy/` noch `scripts/` noch die GitHub-Workflows referenzieren das Vorhaben; der einzige Treffer auf „react“ in `.github/workflows/e2e-smokes.yml` ist der Report-Datenfeldname `generate_section_react` und hat keinen Bezug zum Frontend,
- das Root-`package.json` definiert weder Workspaces noch einen `frontend-next`-Eintrag,
- der React-Code liegt vollständig außerhalb dieses Repositories.

Das ausgelieferte Produktfrontend von Agora ist unverändert das Vue-Frontend unter `frontend/`.

---

## Abgrenzung

Dieses Dokument ist ein abgeschlossener Untersuchungsbefund zu #836, keine Planungsdatei und keine konkurrierende Statusquelle. Verbindlich bleiben `README.md`, `docs/STATUS.md`, `ROADMAP.md` und die GitHub Issues in der in [`AGENTS.md`](../../../AGENTS.md) festgelegten Reihenfolge.

Die aus dem Befund abgeleitete Folgearbeit wird ausschließlich über Issues geführt, nicht hier:

- die Release-Einordnung des React-/Lovable-Vorhabens → #837
- die Doku-Stolpersteine dieses Verzeichnisses (Ablage von `SLICE-5.2`, irreführende Branch-Namen, veraltete `brief.md`-Stand-Zeile) → #910

Sobald #837 die Einordnung in `ROADMAP.md` und `docs/STATUS.md` verankert hat, ist dieses Dokument nur noch Beleg-Archiv für die dort getroffene Aussage.

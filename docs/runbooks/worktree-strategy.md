# Worktree-Strategie

Datei: `docs/runbooks/worktree-strategy.md` · Stand: 2026-08-02

## Prinzip

Jeder Sub-Slice läuft in einem isolierten Git-Worktree. Kein Slice teilt sich
einen Workspace mit einem anderen. Das verhindert Filesystem-Konflikte,
versehentliche Cross-Slice-Edits und macht Rollbacks trivial.

---

## Pfad-Konvention

```
/Volumes/T7/Worktrees/agora/<slice-id>/
```

Beispiele:
- `/Volumes/T7/Worktrees/agora/P1.1/` — Pflichtabschnitt-Validator
- `/Volumes/T7/Worktrees/agora/R4/` — Evidence-Routing aktivieren
- `/Volumes/T7/Worktrees/agora/mai-17-radon/` — Komplexitäts-Gate

Neue Agora-Worktrees werden direkt auf T7 angelegt. `/private/tmp` ist für
Worktrees verboten; Symlinks von dort auf T7 sind unnötig und verschleiern den
tatsächlichen Speicherort. Historische Handover dürfen ihre damaligen
`/private/tmp`-Pfade unverändert dokumentieren.

Diese Konvention gilt für **manuell per `git worktree add` angelegte**
Worktrees. Für harness-isolierte Subagent-Worktrees gilt der nächste Abschnitt.

---

## Harness-isolierte Subagent-Worktrees

Subagenten, die mit `isolation: worktree` dispatcht werden, bekommen ihren
Worktree **von der Agent-Runtime zugewiesen**, nicht vom Lead:

```
/Volumes/T7/Projekte/agora/.claude/worktrees/agent-<agent-id>/
Branch: worktree-agent-<agent-id>
```

Dieser Pfad ist **zulässig und der Normalfall** bei Subagent-Dispatch. Er ist
keine Verletzung der T7-Konvention, sondern liegt außerhalb ihres
Geltungsbereichs.

**Warum die T7-Konvention hier nicht greift:** Ein PreToolUse-Hook der Runtime
sperrt für einen isolierten Subagenten jede Git-Operation außerhalb seines
eigenen Worktrees. Ein vom Lead auf T7 vorbereiteter Pfad ist für einen solchen
Worker nicht erreichbar — der Versuch, dorthin zu wechseln, wird aktiv
blockiert. Die Sperre ist eine Permission-Entscheidung, keine Empfehlung; sie
lässt sich nicht umgehen und soll es auch nicht.

**Konsequenzen für den Lead:**

- Für Worker mit `isolation: worktree` **keinen** T7-Worktree vorbereiten und
  keinen Zielpfad im Briefing vorgeben. Das erzeugt nur einen Konflikt, den der
  Worker korrekterweise meldet, statt zu arbeiten.
- Der Worker committet auf seinem `worktree-agent-<id>`-Branch. Der Lead
  übernimmt das Ergebnis anschließend selbst — per `git cherry-pick` auf einen
  sprechend benannten Branch oder durch Branch-Umbenennung vor dem PR.
- Ein Worker, der ohne `isolation: worktree` läuft, arbeitet weiterhin im
  Repo-Root oder in einem vom Lead angelegten T7-Worktree. Dort gilt die
  Pfad-Konvention oben unverändert.
- Harness-Worktrees sind kurzlebig und können bei Prozess-Neustart oder
  Systemabsturz verschwinden. Vor dem Aufräumen prüfen, ob dort noch
  uncommittete Arbeit liegt (`git -C <pfad> status --short`).

---

## Workflow

### Slice starten

```bash
# Aus dem Repo-Root, auf dem aktuellen Branch
test -d /Volumes/T7 || { printf '%s\n' 'Fehler: T7 ist nicht gemountet' >&2; exit 1; }
git worktree add /Volumes/T7/Worktrees/agora/<slice-id> -b feat/<slice-id>-<name>
cd /Volumes/T7/Worktrees/agora/<slice-id>
```

### Slice beenden (erfolgreich)

```bash
# Nach erfolgreichem Merge in main
cd /Volumes/T7/Projekte/agora
git worktree remove /Volumes/T7/Worktrees/agora/<slice-id>
git branch -d feat/<slice-id>-<name>
```

### Slice abbrechen

```bash
cd /Volumes/T7/Projekte/agora
git -C /Volumes/T7/Worktrees/agora/<slice-id> status --short
# Nur bei leerer Statusausgabe:
git worktree remove /Volumes/T7/Worktrees/agora/<slice-id>
git branch -d feat/<slice-id>-<name>
```

Bei einem sauberen Worktree normal mit `git worktree remove` aufräumen. Falls
ausschließlich regenerierbare ungetrackte Verzeichnisse wie `node_modules`,
`.venv` oder `dist` das Entfernen blockieren, diese nach Prüfung gezielt löschen
und den Befehl erneut ausführen. `git branch -d` funktioniert nur ohne
ungemergte Commits. Sind solche Commits vorhanden, stoppen; `git branch -D` ist
erst nach expliziter Freigabe zum Verwerfen erlaubt. Gleiches gilt bei echten
lokalen Änderungen: kein automatisches `--force` oder `branch -D`.

---

## Multi-Slice-Epic

Bei Epics, die mehrere parallele Slices umfassen (z.B. Observability),
werden Worktrees pro Slice angelegt. Kein „Sammel-Worktree“ für mehrere
Slices — jeder Slice hat seinen eigenen.

---

## Hygiene

### Was NIEMALS in einen Worktree gehört

- `.env`-Dateien mit echten Secrets (Worktrees können länger leben als gedacht)
- Node modules, `__pycache__`, `.venv` — werden bei `git worktree add` nicht
  kopiert, müssen neu installiert werden
- Docker-Volumes oder Datenbank-Dumps

### Aufräumen

```bash
# Alle aktiven Worktrees anzeigen
git worktree list

# Verwaiste Worktrees finden (Branch existiert nicht mehr)
git worktree list | while read wt _ branch; do
  [ "$branch" = "(detached" ] && continue
  git rev-parse --verify "$branch" >/dev/null 2>&1 || echo "ORPHAN: $wt → $branch"
done
```

Einmal pro Woche (Montag) verwaiste Worktrees aufräumen.

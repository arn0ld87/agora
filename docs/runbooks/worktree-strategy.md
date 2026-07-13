# Worktree-Strategie

Datei: `docs/runbooks/worktree-strategy.md` · Stand: 2026-07-13

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

---

## Workflow

### Slice starten

```bash
# Aus dem Repo-Root, auf dem aktuellen Branch
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
```

Bei einem sauberen Worktree normal mit `git worktree remove` und `git branch -d`
aufräumen. Falls ausschließlich regenerierbare ungetrackte Verzeichnisse wie
`node_modules`, `.venv` oder `dist` das Entfernen blockieren, diese nach Prüfung
gezielt löschen und `git worktree remove` erneut ausführen. Bei echten lokalen
Änderungen stoppen und erst nach expliziter Freigabe verwerfen; kein
automatisches `--force` oder `branch -D`.

---

## Multi-Slice-Epic

Bei Epics, die mehrere parallele Slices umfassen (z.B. Observability),
werden Worktrees pro Slice angelegt. Kein „Sammel-Worktree" für mehrere
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

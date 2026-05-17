# Worktree-Strategie

Datei: `docs/runbooks/worktree-strategy.md` · Stand: 2026-05-17

## Prinzip

Jeder Sub-Slice läuft in einem isolierten Git-Worktree. Kein Slice teilt sich
einen Workspace mit einem anderen. Das verhindert Filesystem-Konflikte,
versehentliche Cross-Slice-Edits und macht Rollbacks trivial.

---

## Pfad-Konvention

```
/private/tmp/agora-<slice-id>/
```

Beispiele:
- `/private/tmp/agora-P1.1/` — Pflichtabschnitt-Validator
- `/private/tmp/agora-R4/` — Evidence-Routing aktivieren
- `/private/tmp/agora-mai-17-radon/` — Komplexitäts-Gate

`/private/tmp/` ist auf macOS Apple Silicon ein APFS-Volume, nicht in iCloud/Time Machine,
und wird bei Reboots nicht automatisch bereinigt.

---

## Workflow

### Slice starten

```bash
# Aus dem Repo-Root, auf dem aktuellen Branch
git worktree add /private/tmp/agora-<slice-id> -b feat/<slice-id>-<name>
cd /private/tmp/agora-<slice-id>
```

### Slice beenden (erfolgreich)

```bash
# Nach erfolgreichem Merge in main
cd /Volumes/T7/Projekte/agora
git worktree remove /private/tmp/agora-<slice-id>
git branch -d feat/<slice-id>-<name>
```

### Slice abbrechen

```bash
cd /Volumes/T7/Projekte/agora
git worktree remove --force /private/tmp/agora-<slice-id>
git branch -D feat/<slice-id>-<name>
```

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

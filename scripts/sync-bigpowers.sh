#!/usr/bin/env bash
# Overlay der Bigpowers-Tooling-Dateien ins Repo, als relative Symlinks auf
# node_modules/bigpowers. AGORA-eigene Dateien werden nie ueberschrieben.
#
# Die Symlinks sind maschinenlokale Build-Artefakte und gehoeren nicht ins
# Repo. Sie werden deshalb in der Ausschlussliste des Git-Verzeichnisses
# eingetragen (info/exclude, nicht versioniert) statt in .gitignore. Auf
# jedem Klon stellt dieses Skript Overlay und Ausschluss gemeinsam her.
#
#   bun run bigpowers:sync         # Overlay + Ausschlussliste
#   bash scripts/sync-bigpowers.sh --exclude-only
#   bash scripts/sync-bigpowers.sh --check        # Exit 1 bei Drift
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEP="$ROOT/node_modules/bigpowers"

BEGIN='# >>> BIGPOWERS-OVERLAY BEGIN (generiert von scripts/sync-bigpowers.sh) >>>'
END='# <<< BIGPOWERS-OVERLAY END <<<'

# In einem linked worktree ist ``.git`` eine Datei, kein Verzeichnis — ein
# hartkodiertes "$ROOT/.git/info/exclude" scheitert dort an ``mkdir`` mit
# "Not a directory". Das Repo arbeitet ausgiebig mit Worktrees
# (docs/runbooks/worktree-strategy.md), also fragt das Skript Git nach dem
# gemeinsamen Git-Verzeichnis. ``--git-common-dir`` ist richtig und nicht
# ``--git-dir``: info/exclude teilen sich alle Worktrees eines Repos.
resolve_exclude_path() {
    local git_dir
    if ! git_dir="$(git -C "$ROOT" rev-parse --path-format=absolute --git-common-dir 2>/dev/null)"; then
        echo "FEHLER: $ROOT ist kein Git-Repository." >&2
        return 1
    fi
    printf '%s/info/exclude\n' "$git_dir"
}

relpath() {
    python3 -c 'import os,sys; print(os.path.relpath(sys.argv[1], os.path.dirname(sys.argv[2])))' "$1" "$2"
}

# Alle Links, die das Overlay herstellen SOLL: "<ziel>\t<quelle>" je Zeile,
# abgeleitet aus der Dependency. Bewusst nicht aus dem Dateisystem des Repos
# — sonst kann der Check nicht bemerken, dass das Overlay ganz fehlt.
expected_links() {
    if [[ -d "$DEP/scripts" ]]; then
        find "$DEP/scripts" -type f -print0 | while IFS= read -r -d '' src; do
            printf '%s\t%s\n' "$ROOT/scripts/${src#"$DEP/scripts/"}" "$src"
        done
    fi
    if [[ -d "$DEP/skills" ]]; then
        find "$DEP/skills" -mindepth 1 -maxdepth 1 -type d -print0 | while IFS= read -r -d '' src; do
            printf '%s\t%s\n' "$ROOT/.claude/skills/$(basename "$src")" "$src"
        done
    fi
}

# Alle Links, die das Overlay TATSAECHLICH hergestellt hat.
actual_links() {
    ( cd "$ROOT" && find scripts .claude/skills -type l 2>/dev/null \
        -exec sh -c 'readlink "$1" | grep -q node_modules/bigpowers && printf "%s\n" "$1"' _ {} \; )
}

# Repo-relative Ausschlussmuster, aus den erwarteten Links abgeleitet.
overlay_patterns() {
    expected_links | cut -f1 | sed "s|^$ROOT/|/|" | LC_ALL=C sort
}

link_one() {
    local src="$1" dst="$2" label="$3"
    if [[ -e "$dst" && ! -L "$dst" ]]; then
        echo "  KONFLIKT (AGORA-eigen, uebersprungen): $label"
        return 0
    fi
    [[ -L "$dst" ]] && rm "$dst"
    mkdir -p "$(dirname "$dst")"
    ln -s "$(relpath "$src" "$dst")" "$dst"
}

# Links, die frueher zum Overlay gehoerten und in der aktuellen Dependency
# nicht mehr vorkommen. Ein Bigpowers-Upgrade, das ein Skript entfernt oder
# umbenennt, liess den alten Link sonst als kaputten Rest stehen: --check
# meldete Drift und empfahl genau den Sync, der ihn nicht anfassen konnte.
prune_stale_links() {
    local expected_file removed=0 link
    expected_file="$(mktemp)"
    expected_links | cut -f1 | LC_ALL=C sort > "$expected_file"

    while IFS= read -r link; do
        [[ -n "$link" ]] || continue
        if ! grep -qxF "$ROOT/$link" "$expected_file"; then
            rm -f "$ROOT/$link"
            echo "  ENTFERNT (nicht mehr in der Dependency): $link"
            removed=$((removed + 1))
        fi
    done < <(actual_links)

    rm -f "$expected_file"
    [[ "$removed" -gt 0 ]] && echo "  $removed veraltete(r) Link(s) entfernt."
    return 0
}

sync_links() {
    local dst src rel
    while IFS=$'\t' read -r dst src; do
        [[ -n "$dst" ]] || continue
        rel="${dst#"$ROOT"/}"
        link_one "$src" "$dst" "$rel"
    done < <(expected_links)
}

render_exclude_section() {
    printf '%s\n' "$BEGIN"
    cat <<'HEAD'
# Maschinenlokale Symlinks aus node_modules/bigpowers.
# Regenerieren: bash scripts/sync-bigpowers.sh --exclude-only
# AGORA-eigene Dateien in scripts/ und .claude/skills/ stehen hier NICHT
# und bleiben normal versionierbar.
HEAD
    overlay_patterns
    cat <<'TAIL'
# Bigpowers-Lifecycle-Cockpit: ungenutzt. AGORA steuert ueber PLAN.md,
# docs/STATUS.md, ROADMAP.md und GitHub Issues (siehe AGENTS.md).
/specs/
# Einmaliges Backup aus der Bigpowers-Integration.
/scripts.backup-before-bigpowers/
TAIL
    printf '%s\n' "$END"
}

write_exclude() {
    local exclude patterns_file
    exclude="$(resolve_exclude_path)"
    mkdir -p "$(dirname "$exclude")"
    touch "$exclude"

    # Alte Marker-Sektion und unmarkierte Alt-Eintraege derselben Pfade
    # entfernen. Geloescht werden ausschliesslich Zeilen, die exakt einem
    # verwalteten Muster entsprechen — Fremdeintraege bleiben unberuehrt.
    patterns_file="$(mktemp)"
    { overlay_patterns; printf '/specs/\n/scripts.backup-before-bigpowers/\n'; } > "$patterns_file"

    python3 - "$exclude" "$patterns_file" <<'PY'
import pathlib, re, sys

target = pathlib.Path(sys.argv[1])
managed = {line.strip() for line in pathlib.Path(sys.argv[2]).read_text().splitlines() if line.strip()}

text = target.read_text()
text = re.sub(
    r"\n?# >>> BIGPOWERS-OVERLAY BEGIN.*?# <<< BIGPOWERS-OVERLAY END <<<\n",
    "\n",
    text,
    flags=re.S,
)
kept = [line for line in text.splitlines() if line.strip() not in managed]
target.write_text("\n".join(kept).rstrip("\n") + "\n")
PY

    { printf '\n'; render_exclude_section; } >> "$exclude"
    rm -f "$patterns_file"
    echo "  ${exclude/#"$HOME"/\~}: $(overlay_patterns | wc -l | tr -d ' ') Symlinks ausgeschlossen"
}

# Prueft gegen die ERWARTETEN Links, nicht gegen die vorhandenen. Ein
# fehlendes Overlay ist damit ein Befund und kein leerer Durchlauf.
check_drift() {
    local expected=0 missing=0 broken=0 conflicts=0 stale=0 unignored=0
    local dst src rel ignore_file expected_file link

    if [[ ! -d "$DEP" ]]; then
        echo "DRIFT: Bigpowers ist nicht installiert ($DEP fehlt)."
        echo "Behebung: bun install && bun run bigpowers:sync"
        return 1
    fi

    ignore_file="$(mktemp)"
    expected_file="$(mktemp)"

    while IFS=$'\t' read -r dst src; do
        [[ -n "$dst" ]] || continue
        expected=$((expected + 1))
        rel="${dst#"$ROOT"/}"
        printf '%s\n' "$dst" >> "$expected_file"

        if [[ -e "$dst" && ! -L "$dst" ]]; then
            # Bewusst uebersprungen: eine echte AGORA-Datei gleichen Namens.
            conflicts=$((conflicts + 1))
            continue
        fi
        if [[ ! -L "$dst" ]]; then
            echo "DRIFT: Link fehlt: $rel"
            missing=$((missing + 1))
            continue
        fi
        if [[ ! -e "$dst" ]]; then
            echo "DRIFT: Link zeigt ins Leere: $rel"
            broken=$((broken + 1))
            continue
        fi
        printf '%s\n' "$rel" >> "$ignore_file"
    done < <(expected_links)

    # Verwaiste Links: zeigen auf die Dependency, sind aber nicht erwartet.
    LC_ALL=C sort -o "$expected_file" "$expected_file"
    while IFS= read -r link; do
        [[ -n "$link" ]] || continue
        if ! grep -qxF "$ROOT/$link" "$expected_file"; then
            echo "DRIFT: veralteter Link aus einer frueheren Version: $link"
            stale=$((stale + 1))
        fi
    done < <(actual_links)

    # Ein Aufruf statt einer je Pfad — 300 Prozessstarts sind spuerbar.
    if [[ -s "$ignore_file" ]]; then
        unignored=$(
            cd "$ROOT" \
                && git check-ignore --stdin --non-matching --verbose < "$ignore_file" 2>/dev/null \
                | grep -c '^::' || true
        )
        if [[ "$unignored" -gt 0 ]]; then
            echo "DRIFT: $unignored Link(s) sind nicht ausgeschlossen."
        fi
    fi

    rm -f "$ignore_file" "$expected_file"

    if (( missing + broken + stale + unignored == 0 )); then
        echo "Overlay konsistent: $expected erwartete Links, davon $conflicts AGORA-eigen (uebersprungen)."
        return 0
    fi
    echo "Behebung: bun run bigpowers:sync"
    return 1
}

if [[ ! -d "$DEP" ]]; then
    if [[ "${1:-}" == "--check" ]]; then
        check_drift
        exit $?
    fi
    echo "FEHLER: Bigpowers nicht installiert. Ausfuehren: bun install"
    exit 1
fi

case "${1:-}" in
    --check)        check_drift; exit $? ;;
    --exclude-only) echo "Regeneriere Ausschlussliste..."; write_exclude; exit 0 ;;
    "")             ;;
    *)              echo "Unbekannte Option: $1"; exit 2 ;;
esac

echo "Synchronisiere Bigpowers-Overlay (v$(node -p "require('$DEP/package.json').version"))..."
echo "Veraltete Links:"
prune_stale_links
echo "Links:"
sync_links
echo "Ausschlussliste:"
write_exclude

echo
echo "Overlay aktualisiert."

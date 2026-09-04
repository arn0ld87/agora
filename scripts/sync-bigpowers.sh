#!/usr/bin/env bash
# Overlay der Bigpowers-Tooling-Dateien ins Repo, als relative Symlinks auf
# node_modules/bigpowers. AGORA-eigene Dateien werden nie ueberschrieben.
#
# Die Symlinks sind maschinenlokale Build-Artefakte und gehoeren nicht ins
# Repo. Sie werden deshalb in .git/info/exclude eingetragen (lokal, nicht
# versioniert) statt in .gitignore. Auf jedem Klon stellt dieses Skript
# Overlay und Ausschluss gemeinsam her.
#
#   bun run bigpowers:sync         # Overlay + Ausschlussliste
#   bash scripts/sync-bigpowers.sh --exclude-only
#   bash scripts/sync-bigpowers.sh --check        # Exit 1 bei Drift
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEP="$ROOT/node_modules/bigpowers"
EXCLUDE="$ROOT/.git/info/exclude"

BEGIN='# >>> BIGPOWERS-OVERLAY BEGIN (generiert von scripts/sync-bigpowers.sh) >>>'
END='# <<< BIGPOWERS-OVERLAY END <<<'

relpath() {
    python3 -c 'import os,sys; print(os.path.relpath(sys.argv[1], os.path.dirname(sys.argv[2])))' "$1" "$2"
}

link_one() {
    local src="$1" dst="$2" label="$3"
    if [[ -e "$dst" && ! -L "$dst" ]]; then
        echo "  KONFLIKT (AGORA-eigen, uebersprungen): $label"
        return 0
    fi
    [[ -L "$dst" ]] && rm "$dst"
    ln -s "$(relpath "$src" "$dst")" "$dst"
}

# link_tree <quelle> <ziel> <files|dirs>
link_tree() {
    local src="$1" dst="$2" mode="$3" entry rel
    [[ -d "$src" ]] || { echo "  uebersprungen (fehlt): ${src#"$ROOT"/}"; return 0; }

    if [[ "$mode" == files ]]; then
        while IFS= read -r -d '' entry; do
            rel="${entry#"$src"/}"
            mkdir -p "$dst/$(dirname "$rel")"
            link_one "$entry" "$dst/$rel" "$rel"
        done < <(find "$src" -type f -print0)
    else
        while IFS= read -r -d '' entry; do
            rel="$(basename "$entry")"
            link_one "$entry" "$dst/$rel" "$rel"
        done < <(find "$src" -mindepth 1 -maxdepth 1 -type d -print0)
    fi
}

# Alle Pfade, die auf node_modules/bigpowers zeigen, repo-relativ mit fuehrendem /.
overlay_paths() {
    ( cd "$ROOT" && find scripts .claude/skills -type l \
        -exec sh -c 'readlink "$1" | grep -q node_modules/bigpowers && printf "/%s\n" "$1"' _ {} \; \
        | LC_ALL=C sort )
}

render_exclude_section() {
    printf '%s\n' "$BEGIN"
    cat <<'HEAD'
# Maschinenlokale Symlinks aus node_modules/bigpowers.
# Regenerieren: bash scripts/sync-bigpowers.sh --exclude-only
# AGORA-eigene Dateien in scripts/ und .claude/skills/ stehen hier NICHT
# und bleiben normal versionierbar.
HEAD
    overlay_paths
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
    mkdir -p "$(dirname "$EXCLUDE")"
    touch "$EXCLUDE"

    # Alte Marker-Sektion und unmarkierte Alt-Eintraege derselben Pfade entfernen.
    # Es werden ausschliesslich Zeilen geloescht, die exakt einem aktuellen
    # Overlay-Pfad entsprechen - Fremdeintraege bleiben unberuehrt.
    local paths_file
    paths_file="$(mktemp)"
    { overlay_paths; printf '/specs/\n/scripts.backup-before-bigpowers/\n'; } > "$paths_file"

    python3 - "$EXCLUDE" "$paths_file" <<'PY'
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

    { printf '\n'; render_exclude_section; } >> "$EXCLUDE"
    rm -f "$paths_file"
    echo "  .git/info/exclude: $(overlay_paths | wc -l | tr -d ' ') Symlinks ausgeschlossen"
}

check_drift() {
    local missing=0 broken
    broken="$( cd "$ROOT" && find scripts .claude/skills -type l ! -exec test -e {} \; -print | wc -l | tr -d ' ' )"
    if [[ "$broken" != 0 ]]; then
        echo "DRIFT: $broken kaputte Symlinks."
        missing=1
    fi
    while IFS= read -r p; do
        if ! ( cd "$ROOT" && git check-ignore -q "${p#/}" ); then
            echo "DRIFT: nicht ausgeschlossen: $p"
            missing=1
        fi
    done < <(overlay_paths)
    if [[ "$missing" == 0 ]]; then
        echo "Overlay konsistent: $(overlay_paths | wc -l | tr -d ' ') Symlinks, alle ausgeschlossen."
    else
        echo "Behebung: bun run bigpowers:sync"
    fi
    return "$missing"
}

if [[ ! -d "$DEP" ]]; then
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
echo "scripts/:"
link_tree "$DEP/scripts" "$ROOT/scripts" files
echo ".claude/skills/:"
link_tree "$DEP/skills" "$ROOT/.claude/skills" dirs
echo "Ausschlussliste:"
write_exclude
echo
echo "Overlay aktualisiert."

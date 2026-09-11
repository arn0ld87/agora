#!/usr/bin/env bash
#
# SessionStart-Hook fuer Claude Code on the web.
#
# Stellt sicher, dass Backend und Frontend in einem frischen Remote-Container
# ohne Handarbeit lauffaehig sind. Laeuft ausschliesslich remote — lokale
# Entwicklungsmaschinen bringen ihre Toolchain selbst mit.
#
# Warum es diesen Hook gibt
# -------------------------
# Das Image liefert uv 0.8.17, dessen Python-Index bei 3.14.0rc2 endet.
# `backend/pyproject.toml` verlangt ">=3.14,<3.15", also waehlt uv genau diese
# Release-Candidate-Version — und pydantic bricht darauf beim Import:
#
#   TypeError: _eval_type() got an unexpected keyword argument
#              'prefer_fwd_module'
#
# pydantic schaltet den Aufruf hinter `sys.version_info >= (3, 14)`. rc2
# erfuellt die Bedingung, hat den Parameter aber noch nicht — der kam erst nach
# dem Release Candidate ins CPython-`typing`. Folge: die gesamte Backend-Suite
# liess sich nicht einmal einsammeln, jeder Test brach beim Collect ab. Das ist
# kein Fehler im Projektcode, sondern eine Vorabversion des Interpreters, auf
# die niemand zielt.
#
# Der Hook beschafft deshalb ein finales 3.14 und baut das venv darauf.
#
set -uo pipefail

# Nur im Remote-Container. Lokal nichts anfassen.
if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

REPO="${CLAUDE_PROJECT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
cd "$REPO" || exit 0

note() { printf '  %s\n' "$*"; }
warn() { printf '  ! %s\n' "$*" >&2; }

# --------------------------------------------------------------------------
# 1. Ein finales CPython 3.14 beschaffen
# --------------------------------------------------------------------------

#: True, wenn der Interpreter existiert und KEINE Vorabversion ist.
is_final_314() {
  local python="$1"
  [ -x "$python" ] || return 1
  "$python" - <<'PY' >/dev/null 2>&1
import sys
v = sys.version_info
raise SystemExit(0 if v[:2] == (3, 14) and v.releaselevel == "final" else 1)
PY
}

#: Neueste python3.14-Version im deadsnakes-Index, leer wenn nicht ermittelbar.
deadsnakes_version() {
  zcat "$1" 2>/dev/null | awk '
    /^Package: python3\.14$/ { inpkg = 1; next }
    inpkg && /^Version: / { print $2; exit }
    /^$/ { inpkg = 0 }
  '
}

install_python_from_deadsnakes() {
  local codename tmp base version pkg rc
  codename="$(. /etc/os-release 2>/dev/null && echo "${VERSION_CODENAME:-noble}")"
  base="https://ppa.launchpadcontent.net/deadsnakes/ppa/ubuntu"
  tmp="$(mktemp -d)" || return 1

  if ! curl -sSfL --max-time 120 \
      -o "$tmp/Packages.gz" \
      "$base/dists/$codename/main/binary-amd64/Packages.gz"; then
    rm -rf "$tmp"
    return 1
  fi

  version="$(deadsnakes_version "$tmp/Packages.gz")"
  if [ -z "$version" ]; then
    rm -rf "$tmp"
    return 1
  fi
  note "installiere CPython $version aus deadsnakes ($codename)"

  # Reihenfolge zaehlt: stdlib vor Interpreter, venv zuletzt.
  for pkg in "libpython3.14-stdlib_${version}_amd64.deb" \
             "python3.14_${version}_amd64.deb" \
             "python3.14-venv_${version}_amd64.deb"; do
    if ! curl -sSfL --max-time 180 -o "$tmp/$pkg" \
        "$base/pool/main/p/python3.14/$pkg"; then
      rm -rf "$tmp"
      return 1
    fi
  done

  # Alle Laufzeit-Abhaengigkeiten (libssl3t64, libsqlite3-0, libffi8, …) sind
  # im Basisimage bereits vorhanden, deshalb genuegt dpkg ohne Paketmanager —
  # das Ubuntu-Hauptarchiv ist aus diesem Container ohnehin nicht erreichbar.
  dpkg -i "$tmp"/*.deb >/dev/null 2>&1
  rc=$?
  rm -rf "$tmp"
  return $rc
}

PYTHON314=""
for candidate in /usr/bin/python3.14 /usr/local/bin/python3.14; do
  if is_final_314 "$candidate"; then
    PYTHON314="$candidate"
    break
  fi
done

if [ -z "$PYTHON314" ]; then
  if install_python_from_deadsnakes && is_final_314 /usr/bin/python3.14; then
    PYTHON314="/usr/bin/python3.14"
  else
    # Zweiter Versuch ueber uv. Greift, sobald das Image ein uv mitbringt,
    # dessen Python-Index ein finales 3.14 kennt.
    warn "deadsnakes nicht verfuegbar — versuche 'uv python install 3.14'"
    uv python install 3.14 >/dev/null 2>&1
    for candidate in "$HOME/.local/bin/python3.14" /usr/bin/python3.14; do
      if is_final_314 "$candidate"; then
        PYTHON314="$candidate"
        break
      fi
    done
  fi
fi

if [ -n "$PYTHON314" ]; then
  note "Python: $("$PYTHON314" -V 2>&1) ($PYTHON314)"
else
  warn "kein finales CPython 3.14 gefunden — das Backend-venv faellt auf die"
  warn "uv-Auswahl zurueck. Ist das eine Vorabversion, scheitert jeder"
  warn "Backend-Test bereits beim Collect (pydantic/prefer_fwd_module)."
fi

# --------------------------------------------------------------------------
# 2. Backend-venv
# --------------------------------------------------------------------------

if [ -d backend ]; then
  # Ein bestehendes venv auf einer Vorabversion ist unbrauchbar — neu bauen.
  if [ -x backend/.venv/bin/python ] && ! is_final_314 backend/.venv/bin/python; then
    note "verwerfe Backend-venv auf Vorabversion"
    rm -rf backend/.venv
  fi

  if [ ! -x backend/.venv/bin/python ] && [ -n "$PYTHON314" ]; then
    (cd backend && uv venv --python "$PYTHON314" >/dev/null 2>&1) \
      || warn "uv venv fehlgeschlagen"
  fi

  # --frozen: exakt die Versionen aus uv.lock, kein Re-Resolve.
  if (cd backend && uv sync --frozen >/dev/null 2>&1); then
    note "Backend-Abhaengigkeiten synchronisiert"
  else
    warn "uv sync --frozen fehlgeschlagen"
  fi

  # Rauchtest: genau der Import, der auf der Vorabversion gebrochen ist.
  if (cd backend && uv run --frozen --no-sync python -c \
        "import pydantic; from app.config import Config" >/dev/null 2>&1); then
    note "Backend-Import ok"
  else
    warn "Backend laesst sich nicht importieren — Tests werden fehlschlagen."
  fi
fi

# --------------------------------------------------------------------------
# 3. Frontend
# --------------------------------------------------------------------------

if [ -f frontend/package.json ] && command -v bun >/dev/null 2>&1; then
  if (cd frontend && bun install --frozen-lockfile >/dev/null 2>&1); then
    note "Frontend-Abhaengigkeiten installiert"
  else
    warn "bun install fehlgeschlagen — 'bun run check' und Vitest laufen nicht"
  fi
fi

# Der Hook darf den Session-Start nie kippen: Diagnose steht oben.
exit 0

# shellcheck shell=bash
#
# Gemeinsame .env-Manipulation der E2E-Skripte (Issue #989).
#
# Wird von scripts/e2e-up.sh und scripts/e2e-down.sh gesourct. Beide brauchen
# dieselbe Logik; sie zweimal zu pflegen hiesse, sicherheitsrelevanten Code zu
# duplizieren.
#
# Der Aufrufer MUSS `agora_env_cleanup_tmp` in seinen EXIT-Trap haengen.
#
# Warum ueberhaupt Temp-Datei + mv statt In-Place-Bearbeitung: das Ersetzen ist
# so atomar, ein abgebrochener Lauf hinterlaesst keine halb geschriebene .env.

# Pfad der aktuell offenen Temp-Datei; leer, wenn keine offen ist.
_AGORA_ENV_TMP=""

# Muss im EXIT-Trap des aufrufenden Skripts stehen.
#
# Ein fester Name wie `.env.tmp` waere nicht von `.gitignore` gedeckt: bricht
# der Lauf zwischen Redirect und `mv` ab, laege eine untracked Datei mit
# AGORA_SECRET_KEY, NEO4J_PASSWORD und AGORA_AUTH_TOKEN im Klartext im
# Worktree, die ein `git add -A` mitnaehme. Daher `mktemp` mit Zufallsnamen
# plus dieser Aufraeumer. `.gitignore` deckt das Muster zusaetzlich ab —
# Verteidigung in zwei Schichten, weil es hier um Secrets geht.
agora_env_cleanup_tmp() {
  if [[ -n "$_AGORA_ENV_TMP" && -f "$_AGORA_ENV_TMP" ]]; then
    rm -f "$_AGORA_ENV_TMP"
  fi
  _AGORA_ENV_TMP=""
}

# Dateimodus der Ziel-Datei auf die Temp-Datei uebernehmen.
#
# Ohne das bekaeme die .env den Modus der Temp-Datei: `>>` erhielt den Modus
# frueher implizit, `mv` ersetzt ihn. Gemessen wurde 0600 -> 0644, also eine
# stille Rechteaufweitung auf einer Datei voller Secrets.
_agora_copy_file_mode() {
  local src="$1" dst="$2" mode
  # --reference gibt es nur in GNU coreutils, nicht auf macOS/BSD.
  if chmod --reference="$src" "$dst" 2>/dev/null; then
    return 0
  fi
  mode="$(stat -f '%Lp' "$src" 2>/dev/null || stat -c '%a' "$src" 2>/dev/null || true)"
  if [[ -n "$mode" ]]; then
    chmod "$mode" "$dst"
  fi
}

# grep-Exit sauber unterscheiden.
#
# 1 heisst "keine Zeile uebrig" und ist hier legitim; ab 2 liegt ein echter
# Fehler vor (unlesbare Datei, Schreibfehler). Ein pauschales `|| true` haette
# den Fehlerfall verschluckt und anschliessend eine abgeschnittene Datei ueber
# die .env geschoben — Verlust der lokalen Dev-Credentials.
_agora_grep_without_key() {
  local key="$1" src="$2" status=0
  grep -v "^${key}=" "$src" || status=$?
  if (( status >= 2 )); then
    echo "::error::[agora-env] grep auf ${src} fehlgeschlagen (exit ${status}) — Datei bleibt unveraendert" >&2
    return "$status"
  fi
  return 0
}

# Neuen Inhalt der .env schreiben: alle Zeilen ausser denen von `key`, optional
# gefolgt von genau einer neuen `key=value`-Zeile.
#
# Jeder Schritt bricht bei Fehlschlag ab, BEVOR `mv` laeuft — auf `set -e` des
# Aufrufers zu bauen waere zu duenn: `mv` ist der destruktive Schritt, und ein
# fehlgeschlagener Aufbau darf die bestehende .env nie ersetzen. Genau das
# passierte in einem Testlauf ohne `set -e`: die Zieldatei wurde durch eine
# leere Temp-Datei ueberschrieben.
#
# Reihenfolge ist bindend: erst Inhalt schreiben, Modus zuletzt setzen. Umgekehrt
# koennte ein restriktiver Quell-Modus (im Extremfall 0000) die Temp-Datei fuer
# die eigenen Schreibzugriffe sperren.
_agora_env_rewrite() {
  local key="$1" env_file="$2" value="${3-}" with_value="$4"
  local tmp

  tmp="$(mktemp "${env_file}.XXXXXX")" || return 1
  _AGORA_ENV_TMP="$tmp"

  if [[ -f "$env_file" ]]; then
    if ! _agora_grep_without_key "$key" "$env_file" >> "$tmp"; then
      agora_env_cleanup_tmp
      return 1
    fi
  fi
  if [[ "$with_value" == "yes" ]]; then
    if ! printf '%s=%s\n' "$key" "$value" >> "$tmp"; then
      agora_env_cleanup_tmp
      return 1
    fi
  fi

  if [[ -f "$env_file" ]]; then
    _agora_copy_file_mode "$env_file" "$tmp"
  else
    chmod 0600 "$tmp"
  fi

  if ! mv "$tmp" "$env_file"; then
    agora_env_cleanup_tmp
    return 1
  fi
  _AGORA_ENV_TMP=""
  return 0
}

# Genau eine Zeile `key=value` in der .env sicherstellen.
#
# Bestehende Definitionen desselben Schluessels werden vorher entfernt, fremde
# Eintraege bleiben unangetastet.
agora_env_upsert() {
  _agora_env_rewrite "$1" "$3" "$2" yes
}

# Alle Zeilen eines Schluessels aus der .env entfernen.
#
# Rueckgabecodes bewusst dreiwertig:
#   0 — entfernt
#   1 — nichts zu tun (Datei fehlt oder Schluessel nicht enthalten)
#   2 — Umschreiben fehlgeschlagen, Datei unveraendert
#
# Waeren 1 und 2 derselbe Code, bliebe ein gescheitertes Aufraeumen im
# EXIT-Trap von e2e-down.sh stumm — und AGORA_E2E_LLM_MODE=stub stuende weiter
# in der .env, also genau der Zustand, den der Trap verhindern soll.
agora_env_drop_key() {
  local key="$1" env_file="$2" probe=0

  [[ -f "$env_file" ]] || return 1

  # Auch die Vorab-Pruefung muss Exit 1 von Exit >=2 trennen. Ein pauschales
  # `|| return 1` deutete eine unlesbare .env als "Schluessel nicht vorhanden"
  # und meldete faelschlich Erfolg — der Stub-Schalter bliebe stehen.
  grep -q "^${key}=" "$env_file" || probe=$?
  if (( probe >= 2 )); then
    echo "::error::[agora-env] ${env_file} ist nicht lesbar (grep exit ${probe})" >&2
    return 2
  fi
  (( probe == 1 )) && return 1

  if ! _agora_env_rewrite "$key" "$env_file" "" no; then
    echo "::error::[agora-env] ${key} konnte nicht aus ${env_file} entfernt werden" >&2
    return 2
  fi
  return 0
}

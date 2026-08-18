#!/usr/bin/env bash
# install-playwright-chromium.sh — Playwright-Chromium installieren, mit Retry.
#
# Der apt-Teil von ``playwright install --with-deps`` zieht Font-Pakete von den
# Ubuntu-Mirrors. Faellt ein Mirror aus, bricht apt mit Exit 100 ab — nicht in
# einen Timeout, sondern sofort. Am 2026-08-18 hat das zwei PRs nacheinander
# rot gemacht ("Could not connect to azure.archive.ubuntu.com:80, connection
# timed out"), jeweils nach gut einer Minute und bevor ein einziger Test lief.
#
# Ein grosszuegigeres Step-Timeout hilft dagegen nicht; das war der Fix fuer
# #1070 und adressiert einen anderen Fall.
#
# Als eigenes Skript und nicht als Inline-``run:``, damit das Verhalten
# testbar ist (tests/scripts/test_install_playwright_chromium.py).
#
# Ueberschreibbar fuer Tests:
#   PLAYWRIGHT_INSTALL_ATTEMPTS  Zahl der Versuche (Default 3)
#   PLAYWRIGHT_RETRY_BASE_DELAY  Sekunden je Versuch, multiplikativ (Default 20)

set -uo pipefail

ATTEMPTS="${PLAYWRIGHT_INSTALL_ATTEMPTS:-3}"
BASE_DELAY="${PLAYWRIGHT_RETRY_BASE_DELAY:-20}"

attempt=1
while [ "$attempt" -le "$ATTEMPTS" ]; do
  if npx playwright install --with-deps chromium; then
    exit 0
  fi
  if [ "$attempt" -ge "$ATTEMPTS" ]; then
    echo "::error::Playwright-Installation nach ${ATTEMPTS} Versuchen fehlgeschlagen."
    exit 1
  fi
  delay=$((attempt * BASE_DELAY))
  echo "::warning::Playwright-Installation fehlgeschlagen (Versuch ${attempt}/${ATTEMPTS}) — neuer Versuch in ${delay}s."
  # Ohne die Aktualisierung greift apt beim naechsten Versuch denselben
  # unerreichbaren Host an; erst sie laesst einen rotierten Mirror wirken.
  # Ein Fehlschlag hier ist kein Grund aufzugeben — der eigentliche Versuch
  # folgt gleich.
  sudo apt-get update || true
  sleep "$delay"
  attempt=$((attempt + 1))
done

echo "::error::Playwright-Installation nach ${ATTEMPTS} Versuchen fehlgeschlagen."
exit 1

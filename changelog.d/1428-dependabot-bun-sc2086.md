### Changed

- Dependabot pflegt Frontend-Abhängigkeiten jetzt über das `bun`-Ökosystem statt
  `npm`. Das npm-Ökosystem aktualisierte nur `package.json` und ließ `bun.lock`
  stehen; der Frontend-Smoke-Gate brach mit „lockfile had changes, but lockfile
  is frozen" ab und jedes Frontend-Update musste manuell nachgezogen werden.
  Ein Wächtertest (`tests/config/test_dependabot_config.py`) verhindert den
  Rückfall. (#1428)
- Der bewusst unquotierte `$PIP_AUDIT_FLAGS`-Aufruf in `ci.yml` trägt eine
  begründete `shellcheck disable=SC2086`-Direktive. reviewdog/actionlint hängte
  den Befund bisher an jeden PR, der `ci.yml` berührte, und blockierte den
  Merge über die Konversationsauflösung. (#1428)

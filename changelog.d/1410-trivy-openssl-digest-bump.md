### Behoben

- **`build-only` lief seit dem 2026-08-28 auf `main` und damit auf jedem PR
  rot.** Der `Trivy container scan` blockierte den Merge jedes offenen PRs,
  auch solcher mit sonst durchweg gruenen Checks. Die Ursache war
  mehrschichtig; alle vier Ebenen sind jetzt geschlossen (#1410):

  1. **openssl (CVE-2026-14456, HIGH)** in `openssl`, `libssl3t64` und
     `openssl-provider-legacy`: installiert `3.5.6-1~deb13u2`, gefixt in
     `3.5.7-1~deb13u2`. Gescannt wird `target: prod`, also genau die Stage,
     die seit #1328 ein `apt-get update && apt-get upgrade -y` traegt. Der
     Upgrade lief trotzdem ins Leere: Der Build-Job zieht `cache-from:
     type=gha`, und solange FROM-Digest und Instruktion unveraendert bleiben,
     serviert BuildKit den alten apt-Layer — die Zeile wird nie neu
     ausgefuehrt. Die prod-Stage haengt jetzt am aktuellen
     `python:3.14-slim`-Digest (`sha256:cad9a2c8...`). Der Bump ersetzt den
     Upgrade nicht, er loest ihn aus.

  2. **unstructured (CVE-2026-71428, CRITICAL)**: `0.18.32` → `0.27.5`. Der
     Bump erzwang einen zweiten Override: unstructured ab 0.24.0 verlangt
     `psutil>=7.2.2`, waehrend `camel-ai` `psutil<6` pinnt — auch in der
     aktuellsten Version 0.2.90, es gibt also keine camel-ai, die beides
     erfuellt. Ohne `psutil>=7.2.2` im Override-Block ist die Resolution
     unloesbar und die CRITICAL bliebe offen. `camel` 0.2.78 importiert
     gegen psutil 7.2.2 sauber, das Backend-Gate ist gruen.

  3. **nltk (CVE-2026-79675 CRITICAL, CVE-2026-78680, CVE-2026-71513)**:
     `3.10.1` → `3.10.3`. nltk stand bis hierher nur im Override-Block und kam
     transitiv ueber unstructured herein — mit 2. (unstructured nutzt jetzt
     spacy statt nltk) fiel es komplett aus `uv.lock`. Das haette nicht nur
     den Pin wirkungslos gemacht, sondern die gesamte
     nltk-Import-Guard-Infrastruktur entkernt: fuenf Tests in
     `tests/test_nltk_import_guard.py` brachen, dazu haengen
     `NLTK_DISABLE_IMPORT_SECURITY=1` im Dockerfile und der Abschnitt
     "nltk-Baseline" in `docs/dependency-risk-register.md` daran. Statt diesen
     Mechanismus abzureissen oder den SSoT-Test
     (`test_pyproject_and_uv_lock_nltk_pin_match`) aufzuweichen, ist nltk
     jetzt eine **explizite** Dependency auf der gefixten 3.10.3. Der Guard
     behaelt seinen Gegenstand; ein Guard-Test skippt sich seit 3.10.3 selbst,
     weil der Import-Hook upstream entfernt wurde — dieser Fall war im Test
     bereits vorgesehen.

  4. **msgpack (GHSA-6v7p-g79w-8964) und setuptools (CVE-2025-47273)**, beide
     HIGH, waren ueber `uv.lock` gar nicht erreichbar: Die venv fuehrt
     setuptools 83.0.0 und kein msgpack. Beide stecken in
     `site-packages/pip/_vendor` — pip 26.2.1 bundelt laut `vendor.txt`
     `msgpack==1.1.2` und `setuptools==70.3.0`. Das prod-Image braucht pip zur
     Laufzeit nicht (die venv kommt fertig aus `backend-build` und enthaelt
     selbst kein pip, gunicorn startet aus `.venv/bin`, der HEALTHCHECK nutzt
     `urllib`), deshalb wird pip dort jetzt entfernt — statt die Funde per
     `.trivyignore` zu unterdruecken. Die `dev`-Stage behaelt pip.

  Nebenwirkung von 2.: `unstructured` 0.27.5 zieht das spaCy-Oekosystem nach
  (17 neue Lock-Eintraege, 5 entfallen). Die 214 Parsing- und Chunking-Tests
  sowie das vollstaendige Backend-Gate laufen unveraendert gruen.

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

  3. **nltk (CVE-2026-79675 CRITICAL, CVE-2026-78680, CVE-2026-71513)** loest
     sich mit 2. von selbst auf: unstructured 0.27.5 nutzt spacy statt nltk,
     nltk faellt aus `uv.lock` heraus und Agora importiert es an keiner Stelle
     selbst. Der Pin `nltk==3.10.3` bleibt als Riegel fuer den Fall stehen,
     dass eine kuenftige Transitive nltk zurueckholt. `NLTK_DISABLE_IMPORT_
     SECURITY=1` im Dockerfile bleibt aus demselben Grund unangetastet.

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

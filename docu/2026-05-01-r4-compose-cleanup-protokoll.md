# R4 — Compose-Cleanup · Arbeitsprotokoll

**Datum:** 2026-05-01
**Slice:** R4

## Implementierung

`docker-compose.yml`: Kommentar über dem `agora`-Service-Block neu formuliert. Der alte „Oder Pre-built Image:"-Kommentar war missverständlich (Reviewer-Befund). Neue Variante macht klar:

- Default ist lokaler Build (`build: .`)
- Wer ein vorgebackenes Image will, ersetzt `build:` durch `image:`
- Beides gleichzeitig ist ungültig — compose ignoriert `image` dann

`docker compose config` validiert sauber, `npm run check` grün.

---
description: AGORAs Jev-Decision-Pilot prüfen oder den Local-Search-Benchmark ausführen.
argument-hint: "[status|benchmark|test]"
allowed-tools: Read, Bash
---

# /jev — AGORA-Decision-Pilot

Interpretiere `$ARGUMENTS` als genau einen der folgenden Unterbefehle. Ohne Argument gilt `status`. Arbeite im Root dieses Repositorys. Gib niemals API-Keys oder Rohwerte aus dem Provider-Secret-Store aus.

## status

Prüfe `backend/app/config.py`, `backend/app/services/decisions/local_search_shadow.py` und `docs/audits/f005-jev-benchmark-local-search.md`. Melde den tatsächlichen Decision-Layer-Modus, den aktiven Shadow-Use-Case und den Stand der Jev-Freigabe. Der bisherige Benchmark ist eine kleine Pilotmessung; er erlaubt keine produktive Jev-Ausführung. `authoritative` darf nicht aktiviert werden.

## benchmark

Führe im Repository-Root aus:

```bash
cd backend && uv run python scripts/jev_benchmark_local_search.py
```

Das Skript verwendet zwölf fest eingebaute Testfälle. Wenn im bestehenden verschlüsselten Provider-Secret-Store kein Key unter `jev` gebunden ist, läuft nur die Rule-Baseline und Jev wird sichtbar übersprungen. Bei gebundenem Key werden Query und Fakt dieser Testfälle im Klartext an TypeSafe AI gesendet. Gib den Exit-Code und die vom Skript gemeldeten Ergebnisse wieder; bezeichne einen übersprungenen Jev-Arm nicht als erfolgreichen Jev-Vergleich. Keine Ergebnisse als Freigabe oder Kalibration ausgeben.

## test

Führe im Repository-Root aus:

```bash
cd backend && uv run pytest tests/services/test_jev_provider.py tests/scripts/test_jev_benchmark_report.py tests/services/decisions/test_local_search_shadow.py -q
```

Berichte den Exit-Code und die Testzusammenfassung. Die mit `integration` markierten Live-API-Tests laufen nur bei bewusst gesetztem `TYPESAFE_API_KEY`.

Bei anderen Argumenten zeige die drei unterstützten Unterbefehle. `on`/`off` sind kein Schalter für AGORA: Die produktive Aktivierung ist nach `docs/audits/f005-jev-benchmark-local-search.md` noch nicht freigegeben. Dieser Repository-Befehl ist unabhängig von einem persönlichen Jev-Prompt-Router außerhalb AGORAs.

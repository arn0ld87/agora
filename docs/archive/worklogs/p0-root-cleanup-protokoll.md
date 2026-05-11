# P0-Protokoll — Root-Cleanup

**Datum:** 2026-04-22

---

## Ziel

Das Wurzelverzeichnis sollte weniger nach einmaligen Hilfsskripten und temporären Notizen aussehen.

Aus dem Root entfernt wurden deshalb Dateien, die keine zentrale Einstiegsfunktion für das Produkt erfüllen:

- `plan.md`
- `SECURITY_REPORT.md`
- `fix_logs.py`
- `format_logs.py`

---

## Neue Ablageorte

### Nach `docs/archive/history/`
- `plan.md` → `docs/archive/history/previous-agent-plan.md`
- `SECURITY_REPORT.md` → `docs/archive/history/security-review-report.md`

### Nach `scripts/logs/`
- `fix_logs.py` → `scripts/logs/fix_logs.py`
- `format_logs.py` → `scripts/logs/format_logs.py`

---

## Begleitende Anpassung

Die beiden Log-Hilfsskripte referenzierten noch `docs/logs/...`.
Da die Arbeitsdokumentation inzwischen unter `docs/` liegt, wurden die Zielpfade auf `docs/logs/...` angepasst.

---

## Bewertung

Der Effekt ist klein, aber sinnvoll:
- Root wird lesbarer
- operative Historie liegt in `docs/archive/history/`
- Einmalskripte liegen nicht mehr auf oberster Ebene

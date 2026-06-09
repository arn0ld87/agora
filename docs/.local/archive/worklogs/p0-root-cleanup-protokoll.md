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

### Nach `docu/history/`
- `plan.md` → `docu/history/previous-agent-plan.md`
- `SECURITY_REPORT.md` → `docu/history/security-review-report.md`

### Nach `scripts/logs/`
- `fix_logs.py` → `scripts/logs/fix_logs.py`
- `format_logs.py` → `scripts/logs/format_logs.py`

---

## Begleitende Anpassung

Die beiden Log-Hilfsskripte referenzierten noch `docs/logs/...`.
Da die Arbeitsdokumentation inzwischen unter `docu/` liegt, wurden die Zielpfade auf `docu/logs/...` angepasst.

---

## Bewertung

Der Effekt ist klein, aber sinnvoll:
- Root wird lesbarer
- operative Historie liegt in `docu/history/`
- Einmalskripte liegen nicht mehr auf oberster Ebene

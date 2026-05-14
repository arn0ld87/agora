---
description: MAI-06 — ReportV3 wird Single Source of Truth, full_report.md nur noch on-demand-Render. HIGH RISK Persistenz-Touch.
allowed-tools: Read, Bash, Grep, Glob, Edit, Write
---

# /fix-mai-06-retire-v2-md — v2-`full_report.md` retiren

## Ziel

ReportV3 ist die einzige Persistenz-Quelle. `full_report.md` wird nicht mehr stumm doppelt geschrieben — es wird nur noch on-demand vom Export-Endpoint aus `render_report_v3()` gerendert. Bestandsreports bleiben lesbar (Read-Pfad bleibt tolerant).

## Voraussetzungen

- Worktree: `/Volumes/T7/Projekte/agora-worktrees/mai-06/`.
- Branch: `feat/mai-06-retire-v2-md`.
- **MAI-02, MAI-03 müssen durch sein** — sonst sind Hypothesen/DataGaps in ReportV3 unvollständig und v3-Render wäre eine Regression gegenüber v2.
- **Opus-Pre-Review-Pflicht** (Persistenz-Touch — kann Bestandsreports unsichtbar machen).
- **PR-Pflicht** (kein direkter FF-Push) wegen High Risk.

## Schritt-für-Schritt

### Schritt 1: Inventur

```bash
cd /Volumes/T7/Projekte/agora-worktrees/mai-06

# Bestandsreports zählen
find backend/uploads/reports -maxdepth 2 -name "full_report.md" | wc -l
find backend/uploads/reports -maxdepth 2 -name "report-v3.json" | wc -l

# Diff zwischen v2-md und v3-render auf 3 Stichproben prüfen
for rid in $(find backend/uploads/reports -maxdepth 2 -name "report-v3.json" | head -3); do
  echo "=== ${rid} ==="
  # Hilfs-Skript läuft per uv run, render_report_v3() lädt das ReportV3
  cd backend && uv run python -c "
from app.services.report_agent.storage import read_report_v3
from app.services.report_agent.markdown_renderer import render_report_v3
import os
report_id = '${rid}'.split('/')[-2]
v3 = read_report_v3(report_id)
if v3:
    print(render_report_v3(v3)[:500])
" && cd ..
done
```

### Schritt 2: assemble_full_report umbauen

`backend/app/services/report_agent/manager.py`:

```python
@classmethod
def assemble_full_report(cls, report_id: str, outline: ReportOutline) -> str:
    """Assembliert die vollständige Markdown-Repräsentation.

    NEU (MAI-06): Schreibt nicht mehr stumm full_report.md auf Disk.
    Stattdessen: Liefert den String, Aufrufer entscheidet selbst.
    Der Export-Endpoint nutzt render_report_v3() für format=md.
    """
    md_content = f"# {outline.title}\n\n"
    md_content += f"> {outline.summary}\n\n"
    md_content += "---\n\n"

    sections = cls.get_generated_sections(report_id)
    evidence_sections = {
        int(section.get("section_index", 0)): section
        for section in (cls.get_evidence_map(report_id) or {}).get("sections", [])
        if section.get("section_index") is not None
    }
    for section_info in sections:
        md_content += section_info["content"]
        evidence_section = evidence_sections.get(int(section_info.get("section_index", 0)))
        hypotheses = render_hypotheses_for_section(evidence_section)
        confidence_markers = render_confidence_markers_for_section(evidence_section)
        annotations = [item for item in (hypotheses, confidence_markers) if item]
        if annotations:
            md_content = md_content.rstrip() + "\n\n" + "\n\n".join(annotations) + "\n\n"

    md_content = cls._post_process_report(md_content, outline)

    # MAI-06: NICHT mehr auf Disk schreiben — nur returnen.
    # Aufrufer ist save_report(), das setzt report.markdown_content.
    logger.info(f"Markdown-String assembliert (in-memory only): {report_id}")
    return md_content
```

### Schritt 3: save_report anpassen

`backend/app/services/report_agent/manager.py::save_report()`:

```python
@classmethod
def save_report(cls, report: Report, *, report_mode: ReportMode = DEFAULT_REPORT_MODE) -> None:
    cls._ensure_report_folder(report.report_id)
    evidence_map = cls.get_evidence_map(report.report_id)
    report.has_evidence = bool(evidence_map and evidence_map.get("sections"))
    report.evidence_sections = len((evidence_map or {}).get("sections", []))
    cls._write_json_atomic(cls._get_report_path(report.report_id), report.to_dict())

    if report.outline:
        cls.save_outline(report.report_id, report.outline)

    # MAI-06: Kein full_report.md-Write mehr.
    # markdown_content bleibt in meta.json (für Frontend-getReport()).
    # Der Markdown-Export läuft über export-Endpoint → render_report_v3().

    if report.status == ReportStatus.COMPLETED and evidence_map:
        try:
            cls.save_report_v3(cls.build_report_v3(report, evidence_map, report_mode=report_mode))
        except ValidationError as exc:
            logger.warning(f"report-v3 artifact skipped for {report.report_id}: {exc}")

    logger.info(f"report saved (v3-only): {report.report_id}")
```

### Schritt 4: Export-Endpoint umstellen

`backend/app/api/report.py` — der `export`-Endpoint bei `format=md`:

```python
@report_bp.route('/<report_id>/export', methods=['GET'])
def export_report(report_id: str):
    fmt = request.args.get('format', 'json')
    # ... bestehende format=json-Logik bleibt ...

    if fmt == 'md':
        from ..services.report_agent.storage import read_report_v3
        from ..services.report_agent.markdown_renderer import render_report_v3

        v3 = read_report_v3(report_id)
        if v3 is None:
            # Bestandsreport ohne v3-Persistenz → Fallback auf in-meta markdown_content
            report = ReportManager.get_report(report_id)
            if report and report.markdown_content:
                md_text = report.markdown_content
            else:
                return json_error("Report nicht gefunden", status=404)
        else:
            md_text = render_report_v3(v3)

        response = Response(md_text, mimetype='text/markdown; charset=utf-8')
        response.headers['Content-Disposition'] = (
            f'attachment; filename="agora-report-{report_id}.md"'
        )
        return response
```

### Schritt 5: Migrations-Skript

`backend/scripts/migrate_v2_full_report_to_v3.py` (neu):

```python
"""MAI-06: Inventar-Skript für Bestandsreports vor v2-Retirement.

Liest alle existierenden full_report.md, prüft ob report-v3.json daneben liegt.
Schreibt einen Audit-Report nach docu/2026-05-14-mai-06-bestandsinventar.md.

NICHT destruktiv — löscht keine Files.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
REPORTS_DIR = REPO_ROOT / "backend" / "uploads" / "reports"
AUDIT_FILE = REPO_ROOT / "docu" / "2026-05-14-mai-06-bestandsinventar.md"


def main() -> int:
    if not REPORTS_DIR.exists():
        print("Keine Bestandsreports — REPORTS_DIR fehlt.")
        return 0

    rows: list[str] = ["| Report-ID | v2-md | v3-json | Status |", "|---|---|---|---|"]
    for report_dir in sorted(REPORTS_DIR.iterdir()):
        if not report_dir.is_dir():
            continue
        v2 = report_dir / "full_report.md"
        v3 = report_dir / "report-v3.json"
        v2_exists = "✓" if v2.exists() else "—"
        v3_exists = "✓" if v3.exists() else "—"
        if v2.exists() and not v3.exists():
            status = "⚠️ Legacy — Export liefert in-meta Fallback"
        elif v3.exists():
            status = "✓ v3-ready"
        else:
            status = "leer"
        rows.append(f"| `{report_dir.name}` | {v2_exists} | {v3_exists} | {status} |")

    AUDIT_FILE.write_text("\n".join([
        "# MAI-06 — Bestands-Inventar Reports",
        "",
        "Erstellt von `backend/scripts/migrate_v2_full_report_to_v3.py` vor v2-Retirement.",
        "",
        *rows,
    ]) + "\n", encoding="utf-8")
    print(f"OK: Inventur unter {AUDIT_FILE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

### Schritt 6: Tests anpassen

`backend/tests/test_report_export.py`:

```python
def test_export_md_uses_v3_render_after_mai_06(tmp_path, monkeypatch):
    """MAI-06: format=md liefert render_report_v3-Output, kein file-read."""
    # ... bestehende Setup-Logik ...
    response = client.get(f'/api/report/{report_id}/export?format=md')
    assert response.status_code == 200
    body = response.data.decode('utf-8')
    assert '# Agora ReportV3' in body  # Render-Header aus markdown_renderer
    assert '**Report-Modus:**' in body
```

### Schritt 7: Inventar vorm Commit

```bash
cd /Volumes/T7/Projekte/agora-worktrees/mai-06
uv run python backend/scripts/migrate_v2_full_report_to_v3.py
cat docu/2026-05-14-mai-06-bestandsinventar.md
```

## Verifikation

```bash
# 1) Voll-Test
cd backend && uv run pytest -x -q

# 2) Bestehende E2E-Tests
cd frontend && npx playwright test minimal-report.spec.ts --reporter=list

# 3) Nach Neu-Generierung: kein NEUES full_report.md
ls -lt backend/uploads/reports/ | head -5
find backend/uploads/reports -name "full_report.md" -newer .git/refs/heads/main
# Erwartet: leer (außer bestehende)

# 4) Export-Endpoint liefert v3-Render
curl -s -H "Authorization: Bearer $AGORA_AUTH_TOKEN" \
  "http://localhost:5001/api/report/<test-report-id>/export?format=md" | head -20
# Erwartet: "# Agora ReportV3", Report-Modus-Banner
```

## Warum?

Doppel-Persistenz ist Wartungslast und Quelle für Drift. ReportV3 ist seit P3.1 die strukturierte Quelle, hat alle Felder (`personas`, `segments`, `claims`, `friction_points`, …). Das v2-Markdown ist nur noch ein Hilfsfeld in `meta.json`. Wenn der Render-Output deterministisch aus v3 erzeugt wird, gibt es keine zwei Quellen mehr, die divergieren können (Bewertung §6.4 „erst strukturierte Rohdaten, dann Aggregation, dann Report").

## Nächste Schritte

1. **PR statt FF-Push** wegen High Risk. PR-Beschreibung verlinkt `docu/2026-05-14-mai-06-bestandsinventar.md`.
2. CHANGELOG: `MAI-06 · ReportV3 ist Single Source of Truth, full_report.md nur noch on-demand-Render.`
3. `/fix-mai-12-fork-safety` nach erfolgreichem Merge.

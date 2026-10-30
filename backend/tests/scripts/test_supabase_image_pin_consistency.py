"""Konsistenztest für Supabase-Image-Pins.

Prüft, dass die in docs/dependency-risk-register.md und
docs/release/0.10.0-rc.1-readiness-report.md (Abschnitt C.1) dokumentierten
aktuellen Image-Pins exakt mit supabase/docker-compose.yml übereinstimmen.
"""

from __future__ import annotations

import re
from pathlib import Path
import yaml

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent


def _get_compose_image_pins() -> set[str]:
    compose_path = _REPO_ROOT / "supabase" / "docker-compose.yml"
    assert compose_path.is_file(), f"Datei nicht gefunden: {compose_path}"
    content = yaml.safe_load(compose_path.read_text(encoding="utf-8"))
    services = content.get("services", {})
    pins: set[str] = set()
    for service in services.values():
        image_val = service.get("image")
        if not image_val:
            continue
        # Extrahiere Default aus ${VAR:-default} oder nimm direkten Wert
        if ":-" in image_val:
            pin = image_val.split(":-", 1)[1].removesuffix("}").strip()
        else:
            pin = image_val.strip()
        pins.add(pin)
    return pins


def _get_readiness_report_table_pins() -> set[str]:
    report_path = _REPO_ROOT / "docs" / "release" / "0.10.0-rc.1-readiness-report.md"
    assert report_path.is_file(), f"Datei nicht gefunden: {report_path}"
    lines = report_path.read_text(encoding="utf-8").splitlines()
    
    # Finde Abschnitt C.1 Tabelle
    in_c1 = False
    pins: set[str] = set()
    for line in lines:
        if "### BLOCKER A" in line:
            in_c1 = True
            continue
        if in_c1 and line.startswith("### BLOCKER B"):
            break
        if in_c1 and line.startswith("| `"):
            # Format: | `supabase/postgres` (`db`) | `17.11.0.013` | ...
            cols = [c.strip() for c in line.split("|")[1:-1]]
            if len(cols) >= 2:
                img_match = re.search(r"`([^`]+)`", cols[0])
                tag_match = re.search(r"`([^`]+)`", cols[1])
                if img_match and tag_match:
                    pins.add(f"{img_match.group(1)}:{tag_match.group(1)}")
    return pins


def _get_dependency_risk_register_update_pins() -> set[str]:
    register_path = _REPO_ROOT / "docs" / "dependency-risk-register.md"
    assert register_path.is_file(), f"Datei nicht gefunden: {register_path}"
    lines = register_path.read_text(encoding="utf-8").splitlines()
    
    in_update_section = False
    pins: set[str] = set()
    for line in lines:
        if "Pin-Update vom 30.10.2026" in line:
            in_update_section = True
            continue
        if in_update_section and (line.startswith("## ") or line.startswith("- **Frist:**")):
            break
        if in_update_section and line.startswith("| `"):
            cols = [c.strip() for c in line.split("|")[1:-1]]
            if cols:
                img_match = re.search(r"`([^`]+)`", cols[0])
                if img_match:
                    pins.add(img_match.group(1))
    return pins


def test_supabase_image_pins_match_compose() -> None:
    compose_pins = _get_compose_image_pins()
    assert len(compose_pins) == 9, f"Erwarte 9 Compose-Images, erhalten: {len(compose_pins)}"

    readiness_pins = _get_readiness_report_table_pins()
    assert readiness_pins == compose_pins, (
        f"Readiness-Report-Tabelle stimmt nicht mit Compose überein!\n"
        f"Diff: {readiness_pins.symmetric_difference(compose_pins)}"
    )

    register_pins = _get_dependency_risk_register_update_pins()
    assert register_pins == compose_pins, (
        f"Dependency-Risk-Register-Tabelle stimmt nicht mit Compose überein!\n"
        f"Diff: {register_pins.symmetric_difference(compose_pins)}"
    )

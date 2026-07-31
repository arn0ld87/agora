"""
Service for exporting reports in various formats (Markdown, JSON, CSV, ZIP).
"""

import io
import json
import os
import tempfile
import zipfile
from datetime import datetime, timezone
from typing import Any, Iterator, Literal, Optional, cast

from pydantic import ValidationError

from ..contracts import (
    EvidenceMapModel,
    ReportContractModel,
    ReportModel,
)
from ..services.evidence_migrations import CURRENT_SCHEMA_VERSION, migrate_v1_to_v2
from ..services.report_agent import ReportManager, ReportStatus
from ..services.report_agent.csv_export import claims_to_csv, personas_to_csv, segments_to_csv
from ..utils.logger import get_logger

logger = get_logger(__name__)

# ZIP-Bundle-Schwellwerte
ZIP_STREAM_THRESHOLD_BYTES: int = 50 * 1024 * 1024   # 50 MB
ZIP_HARD_CAP_BYTES: int = 500 * 1024 * 1024           # 500 MB
CSV_TABLES = frozenset({"personas", "segments", "claims"})


class ReportExportService:
    @staticmethod
    def map_outline_for_contract(outline: Optional[dict[str, Any]]) -> Optional[dict[str, Any]]:
        """Map the dataclass outline shape onto the v2 contract shape."""
        if not outline:
            return None
        sections: list[dict[str, Any]] = []
        for raw in outline.get("sections") or []:
            if not isinstance(raw, dict):
                continue
            sections.append({
                "title": raw.get("title") or "Section",
                "description": raw.get("description") or raw.get("content") or "—",
            })
        return {
            "title": outline.get("title") or "Report",
            "summary": outline.get("summary") or "—",
            "sections": sections,
        }

    @classmethod
    def build_report_contract_model(cls, report_obj) -> ReportModel:
        report_dict = report_obj.to_dict()
        report_dict["schema_version"] = CURRENT_SCHEMA_VERSION
        report_dict["missing_sections"] = list(report_dict.get("missing_sections") or [])
        if report_dict.get("status") == ReportStatus.INCOMPLETE.value:
            report_dict["outline"] = None
        else:
            report_dict["outline"] = cls.map_outline_for_contract(report_dict.get("outline"))
        return ReportModel.model_validate(report_dict)

    @classmethod
    def build_export_envelope(cls, report_obj, raw_evidence_map: Optional[dict[str, Any]]) -> ReportContractModel:
        """Build the v2 export envelope."""
        report = cls.build_report_contract_model(report_obj)

        evidence: Optional[EvidenceMapModel] = None
        migrated = migrate_v1_to_v2(raw_evidence_map) if raw_evidence_map else None
        if migrated:
            try:
                evidence = EvidenceMapModel.model_validate(migrated)
            except ValidationError as exc:
                logger.warning(
                    "Evidence map for report %s is not yet contract-compliant; "
                    "dropped from envelope. First errors: %s",
                    report_obj.report_id,
                    exc.errors(include_url=False)[:3],
                )

        return ReportContractModel(
            schema_version=cast(Literal[2], CURRENT_SCHEMA_VERSION),
            exported_at=datetime.now(timezone.utc),
            report=report,
            evidence=evidence,
        )

    @staticmethod
    def build_csv_export(report_id: str, table: str) -> str:
        """Lädt die passende Datenquelle und gibt RFC-4180-CSV zurück."""
        if table in ("personas", "segments"):
            report_v3 = ReportManager.get_report_v3(report_id) or {}
            if table == "personas":
                return personas_to_csv(report_v3.get("personas") or [])
            return segments_to_csv(report_v3.get("segments") or [])

        # table == "claims"
        evidence_map = ReportManager.get_evidence_map(report_id) or {}
        return claims_to_csv(evidence_map.get("sections") or [])

    @staticmethod
    def build_zip_bundle(report_id: str, report: Any) -> bytes:
        """Baut ein ZIP-Archiv mit allen Report-Artefakten im Speicher."""
        prefix = f"agora-report-{report_id}"
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            md_text = ReportManager.build_report_v3_markdown(report_id)
            if md_text is None:
                md_text = getattr(report, "markdown_content", None)
            if md_text:
                zf.writestr(f"{prefix}/report-v3.md", md_text)

            v3_path = ReportManager._get_report_v3_path(report_id)
            if os.path.exists(v3_path):
                with open(v3_path, encoding="utf-8") as fh:
                    zf.writestr(f"{prefix}/report-v3.json", fh.read())

            evidence_map = ReportManager.get_evidence_map(report_id) or {}
            zf.writestr(
                f"{prefix}/evidence-map.json",
                json.dumps(evidence_map, ensure_ascii=False, indent=2),
            )

            report_v3 = ReportManager.get_report_v3(report_id) or {}
            zf.writestr(
                f"{prefix}/personas.csv",
                personas_to_csv(report_v3.get("personas") or []),
            )
            zf.writestr(
                f"{prefix}/segments.csv",
                segments_to_csv(report_v3.get("segments") or []),
            )
            zf.writestr(
                f"{prefix}/claims.csv",
                claims_to_csv(evidence_map.get("sections") or []),
            )

        return buf.getvalue()

    @staticmethod
    def estimate_zip_size(report_id: str, report: Any) -> int:
        """Schätzt die unkomprimierte Größe der ZIP-Artefakte in Bytes."""
        total = 0

        v3_path = ReportManager._get_report_v3_path(report_id)
        if os.path.exists(v3_path):
            try:
                total += os.path.getsize(v3_path)
            except OSError:
                pass

        md_v3_path = ReportManager._get_report_v3_markdown_path(report_id)
        try:
            total += os.path.getsize(md_v3_path)
        except OSError:
            md_text = getattr(report, "markdown_content", None) or ""
            total += len(md_text) * 2

        evidence_map = ReportManager.get_evidence_map(report_id) or {}
        sections = evidence_map.get("sections") or []
        total += 1024 + len(sections) * 1500

        report_v3 = ReportManager.get_report_v3(report_id) or {}
        total += max(len(report_v3.get("personas") or []) * 200, 100)
        total += max(len(report_v3.get("segments") or []) * 200, 100)
        total += max(len(sections), 1) * 300

        return total

    @staticmethod
    def stream_zip_bundle(report_id: str, report: Any) -> Iterator[bytes]:
        """Streaming-Generator für große ZIP-Bundles."""
        prefix = f"agora-report-{report_id}"
        chunk_size = 64 * 1024

        with tempfile.TemporaryFile() as tmp:
            with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zf:
                md_text = ReportManager.build_report_v3_markdown(report_id)
                if md_text is None:
                    md_text = getattr(report, "markdown_content", None)
                if md_text:
                    zf.writestr(f"{prefix}/report-v3.md", md_text)

                v3_path = ReportManager._get_report_v3_path(report_id)
                if os.path.exists(v3_path):
                    zf.write(v3_path, arcname=f"{prefix}/report-v3.json")

                evidence_map = ReportManager.get_evidence_map(report_id) or {}
                zf.writestr(
                    f"{prefix}/evidence-map.json",
                    json.dumps(evidence_map, ensure_ascii=False, indent=2),
                )

                report_v3 = ReportManager.get_report_v3(report_id) or {}
                zf.writestr(f"{prefix}/personas.csv", personas_to_csv(report_v3.get("personas") or []))
                zf.writestr(f"{prefix}/segments.csv", segments_to_csv(report_v3.get("segments") or []))
                zf.writestr(f"{prefix}/claims.csv", claims_to_csv(evidence_map.get("sections") or []))

            tmp.seek(0)
            while True:
                chunk = tmp.read(chunk_size)
                if not chunk:
                    break
                yield chunk

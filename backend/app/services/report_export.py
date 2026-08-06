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
from ..contracts.report_contract import EvidenceOmissionModel
from ..services.evidence_migrations import (
    CURRENT_SCHEMA_VERSION,
    normalize_persisted_evidence_map,
)
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
        omission: Optional[EvidenceOmissionModel] = None

        # Issue #987: dieselbe kanonische Normalisierung wie der Lese-Pfad
        # GET /api/report/<id>/evidence. Vorher lief hier nur migrate_v1_to_v2,
        # und die restlichen Migrationsschritte fehlten — persistierte
        # Bestands-Maps scheiterten dann am Validator und fielen komplett aus
        # dem Envelope.
        #
        # `is not None` statt Truthiness: eine vorhandene, aber leere
        # evidence-map.json ({}) ist kein fehlendes Artefakt, sondern eine
        # kaputte Map. Mit `if raw_evidence_map` waere sie stumm wie ein
        # fehlendes Artefakt behandelt worden — derselbe stille Verlust eine
        # Ebene tiefer (Codex-Review zu PR #1042).
        migrated = (
            normalize_persisted_evidence_map(raw_evidence_map)
            if raw_evidence_map is not None
            else None
        )
        if migrated is not None:
            try:
                evidence = EvidenceMapModel.model_validate(migrated)
            except ValidationError as exc:
                errors = exc.errors(include_url=False)[:5]
                logger.warning(
                    "Evidence map for report %s is not contract-compliant even "
                    "after migration; dropped from envelope. First errors: %s",
                    report_obj.report_id,
                    errors[:3],
                )
                # Der Fallback bleibt — der Report-Rumpf ist unbeschaedigt und
                # ein Export ohne Evidence ist besser als gar keiner. Er darf
                # nur nicht laenger stumm sein: bis #987 war ein entleerter
                # Envelope von einem Report ohne Evidence nicht zu unterscheiden.
                #
                # `reason` ist der stabile Schluessel — die Oberflaeche
                # uebersetzt daraus per vue-i18n. `detail` ist kein UI-String,
                # sondern die Erklaerung *in der exportierten Datei*: wer sie
                # spaeter ohne Agora oeffnet, soll lesen koennen, warum der
                # Evidence-Teil fehlt (Codex-Review zu PR #1042).
                omission = EvidenceOmissionModel(
                    reason="contract_violation",
                    detail=(
                        "Die Evidence-Map dieses Reports verletzt auch nach der "
                        "Migration den Evidence-Vertrag und wurde deshalb nicht "
                        "exportiert. Der Report-Rumpf ist vollstaendig."
                    ),
                    validation_errors=[
                        f"{'.'.join(str(part) for part in err.get('loc', ()))}: {err.get('msg', '')}"
                        for err in errors
                    ],
                )

        return ReportContractModel(
            schema_version=cast(Literal[2], CURRENT_SCHEMA_VERSION),
            exported_at=datetime.now(timezone.utc),
            report=report,
            evidence=evidence,
            evidence_omitted=omission,
        )

    @staticmethod
    def _normalized_evidence_map(report_id: str) -> dict[str, Any]:
        """Liest die persistierte Evidence-Map und normalisiert sie kanonisch.

        Issue #1036: JSON-, ZIP- und CSV-Export lasen bislang dieselbe
        persistierte ``evidence-map.json`` mit unterschiedlicher Wahrheit —
        nur ``build_export_envelope`` (``?format=json``) migrierte ueber
        ``normalize_persisted_evidence_map`` (siehe Issue #987), waehrend
        ``build_zip_bundle``, ``stream_zip_bundle`` und ``build_csv_export``
        (``table=claims``) die Roh-Map ungeprueft weiterreichten. Ein orphan
        medium-Claim ohne Evidence blieb im ZIP/CSV unveraendert in
        ``claims[]`` stehen, statt — wie im JSON-Export — nach
        ``data_gaps`` migriert zu werden. Alle Export-Formate lesen die
        Evidence-Map jetzt ueber genau diese eine Stelle.
        """
        raw = ReportManager.get_evidence_map(report_id)
        if raw is None:
            return {}
        return normalize_persisted_evidence_map(raw) or {}

    @staticmethod
    def build_csv_export(report_id: str, table: str) -> str:
        """Lädt die passende Datenquelle und gibt RFC-4180-CSV zurück."""
        if table in ("personas", "segments"):
            report_v3 = ReportManager.get_report_v3(report_id) or {}
            if table == "personas":
                return personas_to_csv(report_v3.get("personas") or [])
            return segments_to_csv(report_v3.get("segments") or [])

        # table == "claims"
        evidence_map = ReportExportService._normalized_evidence_map(report_id)
        return claims_to_csv(evidence_map.get("sections") or [])

    @staticmethod
    def _add_budget_usage_to_zip(zf: zipfile.ZipFile, prefix: str, report_id: str) -> None:
        """Verbrauchs- und Budgetdaten des Report-Runs ins Bundle legen (#764).

        Additiv und best-effort: ältere Reports ohne Messdaten erhalten keine
        zusätzlichen Dateien. Enthält niemals Secrets (nur Limits, Provider-
        und Modell-IDs, aggregierte Zähler).
        """
        try:
            from .run_budget import get_run_budget_status
            from .run_registry import RunRegistry
            from .run_usage_ledger import aggregate_usage, load_usage_summary

            runs = RunRegistry().find_by_linked_id("report_id", report_id)
            if not runs:
                return
            run_id = runs[0]["run_id"]

            usage = load_usage_summary(run_id) or aggregate_usage(run_id)
            zf.writestr(f"{prefix}/usage.json", usage.model_dump_json(indent=2))

            budget_status = get_run_budget_status(run_id)
            if budget_status is not None:
                zf.writestr(
                    f"{prefix}/budget.json", budget_status.model_dump_json(indent=2)
                )
        except Exception:  # noqa: BLE001 — Export darf an Zusatzdateien nicht scheitern
            logger.debug("budget/usage zip enrichment skipped", exc_info=True)

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

            # Issue #1036: normalisierte Sicht, nicht die Roh-Map — dieselbe
            # Migrationskette wie der JSON-Export (siehe
            # ``_normalized_evidence_map``), damit ``evidence-map.json`` im
            # ZIP nicht mehr von den anderen Export-Formaten abweicht.
            evidence_map = ReportExportService._normalized_evidence_map(report_id)
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

            ReportExportService._add_budget_usage_to_zip(zf, prefix, report_id)

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

                # Issue #1036: normalisierte Sicht, analog zu
                # ``build_zip_bundle`` — siehe ``_normalized_evidence_map``.
                evidence_map = ReportExportService._normalized_evidence_map(report_id)
                zf.writestr(
                    f"{prefix}/evidence-map.json",
                    json.dumps(evidence_map, ensure_ascii=False, indent=2),
                )

                report_v3 = ReportManager.get_report_v3(report_id) or {}
                zf.writestr(f"{prefix}/personas.csv", personas_to_csv(report_v3.get("personas") or []))
                zf.writestr(f"{prefix}/segments.csv", segments_to_csv(report_v3.get("segments") or []))
                zf.writestr(f"{prefix}/claims.csv", claims_to_csv(evidence_map.get("sections") or []))

                ReportExportService._add_budget_usage_to_zip(zf, prefix, report_id)

            tmp.seek(0)
            while True:
                chunk = tmp.read(chunk_size)
                if not chunk:
                    break
                yield chunk

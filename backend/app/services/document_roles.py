"""Dokument-Rollen eines Projekts für die Report-Evidence (Issue #1240).

Die Rolle wird beim Upload am Dokument-Manifest festgehalten
(``DocumentManifestEntry.document_role``). Die Retrieval-Provenance eines
Graph-Fakts trägt dieselbe ``document_id`` (ADR-0013); über diese Abbildung
bekommt ein Evidence-Item seine Textsorte, ohne dass der Graph selbst eine
weitere Eigenschaft braucht.
"""

from __future__ import annotations

import logging
from typing import Dict, Optional

from ..contracts.document_manifest_contract import DocumentRole
from ..models.project import ProjectManager

logger = logging.getLogger(__name__)


def load_document_roles(project_id: Optional[str]) -> Dict[str, str]:
    """``document_id`` → Rolle für alle Dokumente mit Nicht-Standardrolle.

    Altprojekte ohne Manifest liefern ``{}``: ihre Fakten gelten wie bisher
    als Domänenfakten. Ein unlesbares Manifest ebenfalls — die Rolle ist eine
    Einschränkung, und ihr Fehlen darf den Report nicht abbrechen. Das wird
    geloggt, damit es nicht still passiert.
    """
    if not project_id:
        return {}
    try:
        manifest = ProjectManager.get_document_manifest(project_id)
    except Exception as exc:  # noqa: BLE001 — Manifest ist optional; Report läuft ohne Rollen weiter
        logger.warning(
            "Dokument-Manifest nicht lesbar, Dokument-Rollen entfallen [project_id=%s]: %r",
            project_id,
            exc,
        )
        return {}
    if manifest is None:
        return {}
    return {
        entry.document_id: entry.document_role.value
        for entry in manifest.documents
        if entry.document_role is not DocumentRole.domain_fact
    }


__all__ = ["load_document_roles"]

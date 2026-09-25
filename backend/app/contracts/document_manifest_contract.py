"""Document-Manifest-Contract (Pydantic v2) — ADR-0013 Slice 1, Teil A.

Führt die Dokumentidentität von der Datei-Extraktion bis zum Chunk. Der
Manifest-Sidecar wird neben dem unveränderten ``extracted_text.txt``-Blob
persistiert (``extracted_documents.json``) und ordnet Zeichen-Offsets im
Blob den ursprünglichen Quelldateien zu — ohne den Fließtext selbst um
Marker-Parsing zu erweitern (ein Dokument darf die Trennzeile
``=== Document N: <name> ===`` selbst enthalten, siehe ADR-0013 §1).

Der Anker ``seed_doc:<document_id>#chunk:<chunk_id>`` (ADR-0013 §2) baut auf
diesem Contract auf, wird aber erst in Teil B (Neo4j-Persistenz, Retrieval)
tatsächlich erzeugt und geprüft.

Aufruf zum Schema-Dump:
  cd backend && uv run python -m app.contracts.dump_schemas
"""
from __future__ import annotations

import json
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError

_STRICT = ConfigDict(extra="forbid")


class DocumentRole(str, Enum):
    """Textsorte eines hochgeladenen Dokuments (Issue #1240, Plan-Entscheidung E2).

    Ein Evaluationsdokument mischt sonst drei Textsorten: das Szenario, die
    Fragestellung und die erwarteten Ergebnisse. Ingestiert landen alle drei
    als Seed-Fakt im Graphen — der Report las die mitgelieferten Antworten
    danach als Simulationsbefund.

    Additiv zu ``EvidenceSourceKind`` (ADR-0002 Anker 3 bleibt unberührt): die
    Herkunftsgattung sagt *woher*, die Rolle sagt *welche Art Aussage*.
    """

    domain_fact = "domain_fact"
    scenario_statement = "scenario_statement"
    requirement = "requirement"
    expected_result = "expected_result"
    background = "background"


#: Rollen, deren Aussagen einen Claim nie stützen dürfen — sie beschreiben das
#: Szenario, die Frage oder die erwartete Antwort, nicht die Domäne. Als
#: Kontext bleiben sie abrufbar.
NON_SUPPORTING_DOCUMENT_ROLES: frozenset[str] = frozenset({
    DocumentRole.scenario_statement.value,
    DocumentRole.requirement.value,
    DocumentRole.expected_result.value,
})


_DOCUMENT_ROLES_ADAPTER: TypeAdapter[list[DocumentRole]] = TypeAdapter(list[DocumentRole])


def parse_document_roles(raw: Optional[str], file_count: int) -> list[DocumentRole]:
    """Upload-Formularfeld ``document_roles``: JSON-Liste, eine Rolle je Datei.

    Die Liste folgt der Reihenfolge der ``files``-Teile. Positionen statt
    Dateinamen: zwei Uploads mit gleichem Namen (``results.md`` aus zwei
    Ordnern) sind verschiedene Dokumente und brauchen eigene Rollen
    (Codex-Review PR #1606).

    Leer oder fehlend → alle ``domain_fact``. Ungültiges JSON, eine unbekannte
    Rolle oder eine Länge ungleich der Dateizahl → ``ValueError``. Eine
    stillschweigend verworfene Rolle würde Erwartungstext wieder als
    Domänenfakt ingestieren — genau den Fehler aus #1240.
    """
    if raw is None or not raw.strip():
        return [DocumentRole.domain_fact] * file_count
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError("document_roles must be a valid JSON array") from exc
    try:
        roles = _DOCUMENT_ROLES_ADAPTER.validate_python(payload)
    except ValidationError as exc:
        allowed = ", ".join(role.value for role in DocumentRole)
        raise ValueError(
            f"document_roles must be a list with one of: {allowed}"
        ) from exc
    if len(roles) != file_count:
        raise ValueError(
            f"document_roles must contain exactly one role per file "
            f"({len(roles)} roles for {file_count} files)"
        )
    return roles


class DocumentManifestEntry(BaseModel):
    """Ein Dokument im Manifest: Identität + seine Zeichen-Offsets im Blob."""

    model_config = _STRICT

    document_id: str = Field(
        ...,
        description=(
            "Dateiname ohne Endung; bei Kollision mit laufendem Suffix "
            "eindeutig gemacht (z. B. 'report', 'report-2')."
        ),
    )
    filename: str = Field(..., description="Ursprünglicher Dateiname inklusive Endung.")
    start_offset: int = Field(
        ..., ge=0, description="Erstes Zeichen des Dokumentinhalts im Blob (inklusive)."
    )
    end_offset: int = Field(
        ..., ge=0, description="Erstes Zeichen NACH dem Dokumentinhalt im Blob (exklusive)."
    )
    document_role: DocumentRole = Field(
        default=DocumentRole.domain_fact,
        description=(
            "Textsorte des Dokuments (Issue #1240). Altbestand ohne Angabe "
            "gilt als domain_fact."
        ),
    )


class DocumentManifest(BaseModel):
    """Sidecar-Manifest für einen ``extracted_text.txt``-Blob.

    Persistiert neben dem Blob als ``extracted_documents.json``. Dokumente,
    deren Extraktion fehlgeschlagen ist, tragen keinen Eintrag — der
    Platzhaltertext im Blob ist kein Dokumentinhalt und kann daher auch
    keinen Anker liefern.
    """

    model_config = _STRICT

    documents: list[DocumentManifestEntry] = Field(default_factory=list)


class DocumentAnchoredChunk(BaseModel):
    """Ein Text-Chunk mit Blob-Offset und (falls bekannt) Dokument-Zuordnung.

    Rückgabetyp von ``split_text_into_chunks_with_documents``. Reines
    Zwischenergebnis für Teil B (Neo4j-Persistenz) — noch kein persistiertes
    Artefakt, daher kein eigener Eintrag im Schema-Dump.

    Ohne Manifest (z. B. Altprojekte ohne Sidecar) sind ``document_id`` und
    ``chunk_id`` ``None`` — geraten wird nicht (ADR-0013 §1).
    """

    model_config = _STRICT

    text: str
    start_offset: int = Field(..., ge=0)
    end_offset: int = Field(..., ge=0)
    document_id: Optional[str] = Field(
        default=None,
        description="ID des Dokuments mit dem größten Textanteil in diesem Chunk.",
    )
    chunk_id: Optional[int] = Field(
        default=None,
        description="Laufender Index INNERHALB des Dokuments, beginnend bei 0.",
    )

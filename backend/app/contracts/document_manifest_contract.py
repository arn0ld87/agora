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

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

_STRICT = ConfigDict(extra="forbid")


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

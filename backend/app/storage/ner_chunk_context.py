"""Deterministischer Chunk-Kontext für die NER (Issue #1470, Slice 4.4).

Liefert für jeden Chunk einen kurzen Vorlauftext, der:
  - die letzte Markdown-Überschrift (``#``) oder den letzten
    Dokument-Marker (``=== name ===``) vor dem Chunk enthält, und
  - bis zu 300 Zeichen des Endes des unmittelbar vorherigen Chunks.

Der Kontext wird ausschließlich lesend an die NER übergeben; Chunk-Texte
und Chunk-Grenzen bleiben unverändert (Checkpoint #1472b hängt an
deterministischem Chunking).
"""

from __future__ import annotations

import re
from typing import Optional, Sequence

# Markdown-Überschriften: "# Heading", "## Sub" usw.
_HEADING_RE = re.compile(r"^#{1,6}\s+.+", re.MULTILINE)
# Agora-internes Dokument-Marker-Format: "=== Dokumentname ==="
_DOC_MARKER_RE = re.compile(r"^===\s+.+?\s+===\s*$", re.MULTILINE)

# Vorlauf-Länge aus dem Ende des Vorgänger-Chunks
_TAIL_CHARS: int = 300


def _last_structural_marker(text: str) -> str | None:
    """Gibt den letzten Überschrift- oder Dokument-Marker in *text* zurück.

    Prüft beide Patterns gemeinsam und wählt das Vorkommniss mit der
    höchsten Startposition (= das zuletzt im Text auftretende).
    """
    last: tuple[int, str] | None = None
    for m in _HEADING_RE.finditer(text):
        if last is None or m.start() > last[0]:
            last = (m.start(), m.group().strip())
    for m in _DOC_MARKER_RE.finditer(text):
        if last is None or m.start() > last[0]:
            last = (m.start(), m.group().strip())
    return last[1] if last else None


def _starts_new_document(chunk: str) -> bool:
    """Beginnt der Chunk mit einem Dokument-Marker (``=== name ===``)?"""
    first_line = chunk.lstrip().split("\n", 1)[0] if chunk else ""
    return bool(_DOC_MARKER_RE.match(first_line))


def _is_document_boundary(
    chunks: list[str], document_ids: Optional[Sequence[Optional[str]]], index: int
) -> bool:
    """Wechselt zwischen ``index - 1`` und ``index`` das Dokument?

    Codex-Review PR #1620 (P1): Ohne diese Grenze löste die NER im ersten
    Chunk von Dokument B ein Pronomen gegen eine Entität aus Dokument A auf
    und schrieb die Relation mit der Provenance von B. Mit Manifest
    entscheidet die ``document_id``; ohne (Altprojekte, Neustart-Pfad) der
    Dokument-Marker am Chunk-Anfang.
    """
    if document_ids is not None and document_ids[index] != document_ids[index - 1]:
        return True
    return _starts_new_document(chunks[index])


def build_chunk_contexts(
    chunks: list[str],
    document_ids: Optional[Sequence[Optional[str]]] = None,
) -> list[str]:
    """Berechnet für jeden Chunk einen Kontext-String (pure, deterministisch).

    Für ``chunks[i]`` setzt sich der Kontext zusammen aus:
      1. Der letzten Markdown-Überschrift oder dem letzten Dokument-Marker,
         die/der in einem der vorherigen Chunks desselben Dokuments
         aufgetreten ist. Falls keine gefunden wurde, entfällt dieser Teil.
      2. Den letzten bis zu 300 Zeichen des unmittelbar vorherigen Chunks
         (``chunks[i-1]``), getrimmt — nur innerhalb desselben Dokuments.

    Für ``chunks[0]`` und den ersten Chunk jedes weiteren Dokuments ist der
    Kontext leer.

    Args:
        chunks: Die vollständige, geordnete Liste der Text-Chunks, die auch
                an ``add_text_batches`` übergeben wird.  Darf leere Strings
                enthalten.
        document_ids: optional positionsparallel zu ``chunks`` (Manifest,
                ADR-0013). Ein Wechsel der ID ist eine Dokumentgrenze.

    Returns:
        Eine Liste derselben Länge wie *chunks*.  Einträge können leer sein.
    """
    if document_ids is not None and len(document_ids) != len(chunks):
        raise ValueError("document_ids must have the same length as chunks")
    contexts: list[str] = []
    accumulated_heading: str | None = None

    for i, chunk in enumerate(chunks):
        if i == 0 or _is_document_boundary(chunks, document_ids, i):
            contexts.append("")
            accumulated_heading = None
        else:
            prev_chunk = chunks[i - 1]
            parts: list[str] = []

            # Teil 1: letzte bekannte Überschrift aus vorherigen Chunks
            if accumulated_heading:
                parts.append(accumulated_heading)

            # Teil 2: Vorlauf aus dem Ende des unmittelbaren Vorgängers
            if prev_chunk:
                tail = prev_chunk[-_TAIL_CHARS:].strip()
                if tail:
                    parts.append(tail)

            contexts.append("\n".join(parts) if parts else "")

        # Überschriften dieses Chunks für den nächsten Kontext vorhalten
        heading = _last_structural_marker(chunk)
        if heading is not None:
            accumulated_heading = heading

    return contexts


__all__ = ["build_chunk_contexts"]

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


def build_chunk_contexts(chunks: list[str]) -> list[str]:
    """Berechnet für jeden Chunk einen Kontext-String (pure, deterministisch).

    Für ``chunks[i]`` setzt sich der Kontext zusammen aus:
      1. Der letzten Markdown-Überschrift oder dem letzten Dokument-Marker,
         die/der in einem der vorherigen Chunks (0 … i-1) aufgetreten ist.
         Falls keine gefunden wurde, entfällt dieser Teil.
      2. Den letzten bis zu 300 Zeichen des unmittelbar vorherigen Chunks
         (``chunks[i-1]``), getrimmt.

    Für ``chunks[0]`` ist der Kontext immer leer (kein Vorgänger).

    Args:
        chunks: Die vollständige, geordnete Liste der Text-Chunks, die auch
                an ``add_text_batches`` übergeben wird.  Darf leere Strings
                enthalten.

    Returns:
        Eine Liste derselben Länge wie *chunks*.  Einträge können leer sein.

    Example::

        chunks = ["# Einleitung\\nText A.", "Text B."]
        contexts = build_chunk_contexts(chunks)
        # contexts[0] == ""                              (kein Vorgänger)
        # contexts[1] enthält "# Einleitung" und "Text A."
    """
    contexts: list[str] = []
    accumulated_heading: str | None = None

    for i, chunk in enumerate(chunks):
        if i == 0:
            contexts.append("")
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

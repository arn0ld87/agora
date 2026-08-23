"""
File Parser Utility
Supports text extraction from PDF, Markdown, TXT files.

PDFs are parsed with a hybrid strategy:
  1. Native text layer via PyMuPDF.get_text() — fast, lossless for digital PDFs.
  2. If ENABLE_PDF_VISION is on and a page either has (a) embedded images above
     a size threshold or (b) very little text (likely scanned), the image is
     sent to a vision model and the returned description is inlined as
     "[Abbildung Seite N: …]" / "[Seite N (Scan): …]" so the GraphRAG pipeline
     sees it.

Driven by env:
  ENABLE_PDF_VISION=true|false           (default: false — opt-in, erzeugt Cloud-Calls + Latenz)
  VISION_MODEL_NAME=<ollama model>       (default: gemini-3-flash-preview:cloud)
  VISION_MIN_IMAGE_AREA=<px²>            (default: 40000 — ignore logos/icons)
  VISION_PAGE_SCAN_THRESHOLD=<chars>     (default: 100 — <=N chars triggers full-page render)
  VISION_MAX_DIM=<px>                    (default: 1400 — downscale longer side before encoding)
"""

import base64
import io
import os
from pathlib import Path
from typing import List, Optional, Tuple

from ..contracts.document_manifest_contract import (
    DocumentAnchoredChunk,
    DocumentManifest,
    DocumentManifestEntry,
)


def _read_text_with_fallback(file_path: str) -> str:
    """
    Read text file with automatic encoding detection if UTF-8 fails.

    Uses multi-level fallback strategy:
    1. First try UTF-8 decoding
    2. Use charset_normalizer for encoding detection
    3. Fall back to chardet for encoding detection
    4. Finally use UTF-8 + errors='replace' as fallback

    Args:
        file_path: File path

    Returns:
        Decoded text content
    """
    data = Path(file_path).read_bytes()
    
    # First try UTF-8
    try:
        return data.decode('utf-8')
    except UnicodeDecodeError:
        pass

    # Try charset_normalizer for encoding detection
    encoding = None
    try:
        from charset_normalizer import from_bytes
        best = from_bytes(data).best()
        if best and best.encoding:
            encoding = best.encoding
    except Exception as exc:  # noqa: BLE001 — fallback chain continues with chardet
        _log(f"charset_normalizer detection failed, continuing: {exc}")

    # Fall back to chardet
    if not encoding:
        try:
            import chardet
            result = chardet.detect(data)
            encoding = result.get('encoding') if result else None
        except Exception as exc:  # noqa: BLE001 — fallback chain continues with utf-8 replace
            _log(f"chardet detection failed, continuing: {exc}")

    # Final fallback: use UTF-8 + replace
    if not encoding:
        encoding = 'utf-8'

    return data.decode(encoding, errors='replace')


_PROMPT_FIGURE = (
    "Beschreibe den Inhalt dieser Abbildung (Seite {page}) präzise in 2–5 Sätzen auf Deutsch. "
    "Wenn Text sichtbar ist, transkribiere ihn wörtlich. "
    "Nenne Zahlen, Beschriftungen, Legenden. Falls es ein Diagramm ist, "
    "fasse Aussage, Achsen und Schlüsselwerte zusammen. "
    "Keine Einleitung, keine Meta-Kommentare — direkt mit dem Inhalt starten."
)

_PROMPT_FULL_PAGE = (
    "Dies ist Seite {page} von {total} eines gescannten Dokuments. "
    "Lies den gesamten sichtbaren Text wörtlich und gib ihn strukturiert auf Deutsch wieder. "
    "Erhalte Absätze, Überschriften, Listen, Tabellen (als Markdown-Tabelle falls sinnvoll). "
    "Beschreibe nicht-textuelle Elemente (Bilder, Diagramme) kurz in eckigen Klammern. "
    "Keine Einleitung, direkt mit dem Inhalt starten."
)


def _log(msg: str) -> None:
    try:
        from .logger import get_logger
        get_logger('agora.file_parser').warning(msg)
    except Exception:  # noqa: BLE001 — logging must never raise; print is the last resort
        print(f"[file_parser] {msg}")


def _ensure_png(image_bytes: bytes, ext: str) -> bytes:
    """Convert an arbitrary PDF-embedded image to PNG via Pillow/PyMuPDF fallback."""
    ext = (ext or '').lower()
    if ext in ('png',):
        return image_bytes
    # Try Pillow first (handles jpeg, jp2, tiff, etc.)
    try:
        from PIL import Image
        with Image.open(io.BytesIO(image_bytes)) as im:
            if im.mode not in ('RGB', 'RGBA', 'L'):
                im = im.convert('RGB')
            buf = io.BytesIO()
            im.save(buf, format='PNG', optimize=False)
            return buf.getvalue()
    except Exception as exc:  # noqa: BLE001 — Pillow not available or format unsupported; falls through to PyMuPDF
        _log(f"Pillow PNG conversion failed, trying PyMuPDF: {exc}")
    # Fallback: let PyMuPDF re-encode
    try:
        import fitz
        pix = fitz.Pixmap(image_bytes)
        if pix.alpha:
            pix = fitz.Pixmap(fitz.csRGB, pix)
        return pix.tobytes('png')
    except Exception as exc:  # noqa: BLE001 — last resort: return raw bytes and hope the vision model copes
        _log(f"PyMuPDF PNG conversion failed, returning raw bytes: {exc}")
        return image_bytes


def _downscale_png(image_bytes: bytes, max_dim: int) -> bytes:
    """Downscale a PNG to keep its longer side <= max_dim pixels."""
    try:
        from PIL import Image
        with Image.open(io.BytesIO(image_bytes)) as im:
            w, h = im.size
            if max(w, h) <= max_dim:
                return image_bytes
            ratio = max_dim / float(max(w, h))
            new = (max(1, int(w * ratio)), max(1, int(h * ratio)))
            im = im.convert('RGB') if im.mode not in ('RGB', 'L') else im
            im = im.resize(new, Image.LANCZOS)
            buf = io.BytesIO()
            im.save(buf, format='PNG', optimize=True)
            return buf.getvalue()
    except Exception as exc:  # noqa: BLE001 — Pillow not available; return original bytes unscaled
        _log(f"PNG downscale failed, using original: {exc}")
        return image_bytes


class _VisionHelper:
    """Lazy wrapper around LLMClient.describe_image — survives missing Pillow etc.

    Hartes Cap `VISION_MAX_CALLS_PER_UPLOAD` (Default 40) verhindert, dass ein
    präpariertes PDF mit hunderten kleinen Bildern einen Vision-LLM-Kostenabfluss
    auslöst. Wenn das Limit erreicht ist, werden weitere Calls mit Warning
    übersprungen — der Text-Layer bleibt erhalten.
    """

    def __init__(self):
        self.enabled = False
        self.model: Optional[str] = None
        self.client = None
        self.calls_made = 0
        try:
            self.max_calls = int(os.environ.get('VISION_MAX_CALLS_PER_UPLOAD', '40'))
        except ValueError:
            self.max_calls = 40
        try:
            from .llm_client import LLMClient
            model = os.environ.get('VISION_MODEL_NAME', 'gemini-3-flash-preview:cloud').strip() or None
            self.client = LLMClient(model=model)
            self.model = model
            try:
                self.max_dim = int(os.environ.get('VISION_MAX_DIM', '1400'))
            except ValueError:
                self.max_dim = 1400
            self.enabled = True
        except Exception as exc:  # noqa: BLE001 — vision is optional; log and disable gracefully
            _log(f"vision disabled ({exc})")

    def describe(self, image_bytes: bytes, prompt: str, tag: str = "") -> str:
        if not self.enabled or not image_bytes:
            return ""
        if self.calls_made >= self.max_calls:
            if self.calls_made == self.max_calls:
                _log(
                    f"vision cap reached: {self.max_calls} calls pro Upload. "
                    f"Weitere Bilder werden übersprungen."
                )
                self.calls_made += 1  # nur einmal loggen
            return ""
        try:
            png = _downscale_png(image_bytes, self.max_dim)
            b64 = base64.b64encode(png).decode('ascii')
            self.calls_made += 1
            text = self.client.describe_image(b64, prompt=prompt, mime="image/png")
            return (text or '').strip()
        except Exception as exc:  # noqa: BLE001 — vision call failed; return empty and continue
            _log(f"vision call failed [{tag}]: {exc}")
            return ""


#: Obergrenze für eine ``document_id``. Sie folgt nicht aus dem Dateisystem,
#: sondern aus dem Anker, den ADR-0013 vorschreibt:
#: ``seed_doc:<document_id>#chunk:<chunk_id>`` muss in
#: ``EvidenceItemModel.source_id_anchor`` passen (``max_length=200``, siehe
#: ``contracts/report_contract.py``). Präfix und Chunk-Teil brauchen rund
#: 22 Zeichen, das Kollisionssuffix ein paar weitere — 120 lässt Luft und
#: bleibt für übliche Dateinamen verlustfrei. Ohne diese Grenze erzeugte ein
#: sehr langer Upload-Dateiname erst in Slice 2 einen unauflösbaren Anker
#: (Codex-Review zu PR #1155).
_MAX_DOCUMENT_ID_LENGTH = 120


def derive_document_id(filename: str, existing_ids: set) -> str:
    """Leitet eine ``document_id`` aus einem Dateinamen ab (ohne Endung).

    Der Stamm wird auf ``_MAX_DOCUMENT_ID_LENGTH`` gekürzt, damit der daraus
    gebaute Evidence-Anker in ``source_id_anchor`` passt. Kürzen kann neue
    Kollisionen erzeugen — die fängt derselbe Suffix-Mechanismus ab wie
    gleichnamige Uploads.

    Bei Kollision mit einer bereits vergebenen ID in ``existing_ids`` wird ein
    laufendes Suffix angehängt (``-2``, ``-3``, ...), bis die ID eindeutig
    ist. Der Aufrufer ist dafür verantwortlich, die zurückgegebene ID
    anschließend zu ``existing_ids`` hinzuzufügen (diese Funktion ist rein
    und mutiert das übergebene Set nicht).

    Args:
        filename: Dateiname (mit oder ohne Endung).
        existing_ids: Bereits vergebene document_ids.

    Returns:
        Eindeutige document_id, höchstens ``_MAX_DOCUMENT_ID_LENGTH`` Zeichen
        plus Kollisionssuffix.
    """
    stem = (Path(filename).stem or filename)[:_MAX_DOCUMENT_ID_LENGTH]
    candidate = stem
    suffix = 2
    while candidate in existing_ids:
        candidate = f"{stem}-{suffix}"
        suffix += 1
    return candidate


class FileParser:
    """File Parser"""

    SUPPORTED_EXTENSIONS = {'.pdf', '.md', '.markdown', '.txt'}

    @classmethod
    def extract_text(cls, file_path: str) -> str:
        """
        Extract text from file

        Args:
            file_path: File path

        Returns:
            Extracted text content
        """
        path = Path(file_path)

        if not path.exists():
            raise FileNotFoundError(f"File does not exist: {file_path}")

        suffix = path.suffix.lower()

        if suffix not in cls.SUPPORTED_EXTENSIONS:
            raise ValueError(f"Unsupported file format: {suffix}")

        if suffix == '.pdf':
            return cls._extract_from_pdf(file_path)
        elif suffix in {'.md', '.markdown'}:
            return cls._extract_from_md(file_path)
        elif suffix == '.txt':
            return cls._extract_from_txt(file_path)

        raise ValueError(f"Cannot handle file format: {suffix}")

    @staticmethod
    def _extract_from_pdf(file_path: str) -> str:
        """
        Extract text from PDF. Runs the hybrid text+vision pipeline when
        ENABLE_PDF_VISION is on, otherwise only the PyMuPDF text layer.
        """
        try:
            import fitz  # PyMuPDF
        except ImportError:
            raise ImportError("PyMuPDF required: pip install PyMuPDF")

        # Default: false — PDF-Vision ist opt-in (Cloud-Calls + Latenz).
        # Aktivieren via ENABLE_PDF_VISION=true (i18n-Hinweis: upload.pdfVisionDisabledHint).
        enable_vision = os.environ.get('ENABLE_PDF_VISION', 'false').strip().lower() in ('1', 'true', 'yes', 'on')
        vision = _VisionHelper() if enable_vision else None

        parts: List[str] = []
        with fitz.open(file_path) as doc:
            total = len(doc)
            for idx, page in enumerate(doc, start=1):
                text = (page.get_text() or '').strip()
                page_out: List[str] = []
                if text:
                    page_out.append(text)

                if vision and vision.enabled:
                    try:
                        page_scan_threshold = int(os.environ.get('VISION_PAGE_SCAN_THRESHOLD', '100'))
                    except ValueError:
                        page_scan_threshold = 100

                    # If page has effectively no text layer, assume scanned page
                    # and render the whole page as one image.
                    if len(text) < page_scan_threshold:
                        try:
                            pix = page.get_pixmap(dpi=180)
                            img_bytes = pix.tobytes('png')
                            description = vision.describe(
                                img_bytes,
                                prompt=_PROMPT_FULL_PAGE.format(page=idx, total=total),
                                tag=f"page-{idx}-scan",
                            )
                            if description:
                                page_out.append(f"[Seite {idx} (Scan)]: {description}")
                        except Exception as exc:  # noqa: BLE001 — page render failed; continue with remaining pages
                            _log(f"vision page {idx} failed: {exc}")
                    else:
                        # Describe each substantial embedded image.
                        try:
                            images = page.get_images(full=True)
                        except Exception as exc:  # noqa: BLE001 — page has no image list; skip image processing
                            _log(f"get_images failed for page {idx}, skipping: {exc}")
                            images = []
                        try:
                            min_area = int(os.environ.get('VISION_MIN_IMAGE_AREA', '40000'))
                        except ValueError:
                            min_area = 40000

                        for image_idx, img_meta in enumerate(images, start=1):
                            try:
                                xref = img_meta[0]
                                base = doc.extract_image(xref)
                                data = base.get('image')
                                w = int(base.get('width', 0) or 0)
                                h = int(base.get('height', 0) or 0)
                                ext = (base.get('ext') or 'png').lower()
                                if not data or w * h < min_area:
                                    continue
                                png_bytes = _ensure_png(data, ext)
                                description = vision.describe(
                                    png_bytes,
                                    prompt=_PROMPT_FIGURE.format(page=idx),
                                    tag=f"page-{idx}-img-{image_idx}",
                                )
                                if description:
                                    page_out.append(f"[Abbildung auf Seite {idx}]: {description}")
                            except Exception as exc:  # noqa: BLE001 — image extraction failed; continue with remaining images
                                _log(f"vision image p{idx}-i{image_idx} failed: {exc}")

                if page_out:
                    parts.append("\n\n".join(page_out))

        return "\n\n".join(parts)

    @staticmethod
    def _extract_from_md(file_path: str) -> str:
        """Extract text from Markdown with automatic encoding detection"""
        return _read_text_with_fallback(file_path)

    @staticmethod
    def _extract_from_txt(file_path: str) -> str:
        """Extract text from TXT with automatic encoding detection"""
        return _read_text_with_fallback(file_path)

    @classmethod
    def extract_from_multiple(cls, file_paths: List[str]) -> str:
        """
        Extract text from multiple files and merge

        Rückwärtskompatible Delegation an ``extract_from_multiple_with_manifest``
        (ADR-0013 Slice 1, Teil A, Issue #1152): bestehende Aufrufer, die nur
        den zusammengeführten Text wollen (z. B. ``TextProcessor.extract_from_files``),
        bleiben unverändert lauffähig — das Manifest wird hier verworfen. Wer
        Dokumentidentität braucht, ruft ``extract_from_multiple_with_manifest``
        direkt. Diese Form wurde gewählt statt einer Signaturänderung, weil
        letztere jeden bestehenden Aufrufer angefasst hätte, obwohl nur ein
        Teil der Pipeline (Graph-Build) das Manifest tatsächlich braucht.

        Args:
            file_paths: List of file paths

        Returns:
            Merged text
        """
        text, _manifest = cls.extract_from_multiple_with_manifest(file_paths)
        return text

    @classmethod
    def extract_from_multiple_with_manifest(cls, file_paths: List[str]) -> Tuple[str, DocumentManifest]:
        """
        Wie ``extract_from_multiple``, liefert zusätzlich ein Offset-Manifest.

        Der zurückgegebene Blob ist bitgleich mit dem von ``extract_from_multiple``
        — die Konstruktion pro Dokument-Block ist identisch; zusätzlich werden
        Start-/End-Offset des jeweiligen Dokumentinhalts im gemergten Blob
        mitgezählt. Fehlgeschlagene Extraktionen bekommen keinen
        Manifest-Eintrag: der Platzhaltertext im Blob ist kein Dokumentinhalt
        (ADR-0013 §1).

        Args:
            file_paths: List of file paths

        Returns:
            Tuple aus (gemergter Text, ``DocumentManifest``).
        """
        all_texts: List[str] = []
        documents: List[DocumentManifestEntry] = []
        existing_ids: set = set()
        cumulative = 0

        for i, file_path in enumerate(file_paths, 1):
            if i > 1:
                cumulative += 2  # Länge des "\n\n"-Separators von "\n\n".join(...)

            try:
                text = cls.extract_text(file_path)
                filename = Path(file_path).name
                marker = f"=== Document {i}: {filename} ===\n"
                block = f"{marker}{text}"

                document_id = derive_document_id(filename, existing_ids)
                existing_ids.add(document_id)

                start_offset = cumulative + len(marker)
                end_offset = start_offset + len(text)
                documents.append(
                    DocumentManifestEntry(
                        document_id=document_id,
                        filename=filename,
                        start_offset=start_offset,
                        end_offset=end_offset,
                    )
                )
            except Exception as e:  # noqa: BLE001 — per-file error logged inline; continue extracting remaining files
                block = f"=== Document {i}: {file_path} (extraction failed: {str(e)}) ==="

            all_texts.append(block)
            cumulative += len(block)

        merged_text = "\n\n".join(all_texts)
        return merged_text, DocumentManifest(documents=documents)


#: Issue #1347: Rückblick für den Zeilen-Snap des Folgechunk-Starts.
#: Bewusst fest und bescheiden: Die Ausrichtung soll benachbarte Zeilen
#: einer Aussage (Bedingung + Folgepunkt) im Folgechunk zusammenhalten.
#: Ein mit dem Overlap skalierender Rückblick würde bei großem ``overlap``
#: spürbar mehr, dafür kürzere Chunks erzeugen (mehr Extraktionsaufrufe beim
#: Graph-Build), ohne dort ein zusätzliches Problem zu lösen — große Fenster
#: absorbieren Listenblöcke ohnehin ganz.
_LINE_SNAP_MIN_LOOKBACK = 100


def _snap_to_line_start(
    text: str,
    pos: int,
    *,
    lookback_limit: int,
    lower_bound: int,
) -> Optional[int]:
    """Schiebt ``pos`` auf den Anfang seiner Zeile — innerhalb ``lookback_limit``.

    Issue #1347: Der Wort-Snap allein lässt die Fenstergrenze mitten durch
    mehrzeilige Aussagen (Pfeil-Listen, Aufzählungen) laufen; der Folgechunk
    beginnt dann beim letzten Fragment und verliert die tragende Bedingung an
    den Vorchunk. Die Ausrichtung auf den Zeilenanfang hält solche Einheiten
    im Folgechunk zusammen.

    Bewusst **rückwärts** und **begrenzt**: gesucht wird nur in
    ``[pos - lookback_limit, pos)``. Liegt dort keine Zeilengrenze (typischer
    Fließtextabsatz als eine lange Zeile) oder läge ihr Anfang vor
    ``lower_bound``, wird ``None`` zurückgegeben und der Aufrufer fällt auf
    :func:`_snap_to_word_start` zurück. Der Rückwärtsschritt ist verlustfrei
    (der Start wandert nur rückwärts, es wird nichts übersprungen); das
    Ergebnis ist garantiert ``>= lower_bound`` und strikt progressiv für den
    Aufrufer, solange dieser ``lower_bound = start + 1`` setzt.

    Returns:
        Zeilenanfangsindex (Position hinter dem ``\\n``) oder ``None``.
    """
    search_from = max(pos - lookback_limit, lower_bound)
    if search_from >= pos:
        return None
    newline_pos = text.rfind("\n", search_from, pos)
    if newline_pos == -1:
        return None
    return newline_pos + 1


def _snap_to_word_start(text: str, pos: int, *, lower_bound: int, upper_bound: int) -> int:
    """Schiebt ``pos`` auf einen Wortanfang, ohne Textinhalt zu überspringen.

    Bewusst **rückwärts** gesnappt: liegt ``pos`` mitten in einem Wort, wird
    an den Anfang genau dieses Wortes zurückgegangen. Dadurch kann der Snap
    nie Zeichen zwischen dem Ende des vorigen Chunks und dem neuen Start
    verschlucken — ein Vorwärts-Snap müsste dafür über das Wort hinweg, und
    bei Wörtern, die länger als der Overlap sind, ginge deren Rest verloren.
    Der Rückwärts-Snap vergrößert im schlimmsten Fall den Overlap um eine
    Wortlänge, was fachlich unkritisch ist.

    Args:
        text: Originaltext.
        pos: Gewünschter Startindex (i. d. R. ``end - overlap``).
        lower_bound: Der zurückgegebene Index ist immer ``>= lower_bound``.
            Der Aufrufer setzt hier ``start + 1``, damit die Schleife
            garantiert vorankommt und nicht endlos läuft.
        upper_bound: Obergrenze (das Chunk-Ende ``end``). Wird nur im
            Pathologie-Fall relevant, siehe unten.

    Returns:
        Index eines Wortanfangs. Nur wenn ein einzelnes Wort so lang ist,
        dass weder sein Anfang noch der Anfang des Folgeworts im zulässigen
        Fenster ``[lower_bound, upper_bound]`` liegt (Wort länger als ein
        Chunk, z. B. Base64-Blobs), wird ``max(lower_bound, min(pos,
        upper_bound))`` zurückgegeben. In diesem Pathologie-Fall ist ein
        Mid-Word-Start unvermeidbar; Vorrang haben Terminierung und
        Verlustfreiheit.
    """
    fallback = max(lower_bound, min(pos, upper_bound))

    if pos >= len(text) or pos <= 0:
        return fallback

    # Whitespace-Position: bereits eine saubere Grenze, nur die führenden
    # Leerzeichen überspringen (der Chunk wird ohnehin gestrippt).
    if text[pos].isspace():
        return fallback

    # 1. Rückwärts an den Anfang des Wortes, in dem ``pos`` liegt. Das ist
    #    immer verlustfrei, weil der Start dadurch nur kleiner wird.
    back = pos
    while back > 0 and not text[back - 1].isspace():
        back -= 1
    if back >= lower_bound:
        return back

    # 2. Der Wortanfang liegt vor ``lower_bound`` (das Wort ist lang im
    #    Verhältnis zur Chunk-Größe). Dann vorwärts zum Anfang des
    #    Folgeworts — verlustfrei, solange dieser nicht hinter
    #    ``upper_bound`` (dem Ende des vorigen Chunks) liegt, denn alles bis
    #    dorthin ist bereits ausgeliefert.
    fwd = pos
    while fwd < len(text) and not text[fwd].isspace():
        fwd += 1
    while fwd < len(text) and text[fwd].isspace():
        fwd += 1
    if lower_bound <= fwd <= upper_bound:
        return fwd

    # 3. Pathologie: Wort länger als das gesamte Fenster.
    return fallback


def _chunk_windows(text: str, chunk_size: int, overlap: int) -> List[Tuple[int, int]]:
    """Berechnet die rohen (ungestrippten) Chunk-Fenstergrenzen im Text.

    Extrahiert aus ``split_text_into_chunks`` (ADR-0013 Slice 1, Teil A,
    Issue #1152), damit ein offset-bewusster Chunker
    (``split_text_into_chunks_with_documents``) dieselbe Fenster-Logik nutzen
    kann, ohne sie zu duplizieren — nur die Fenstergrenzen VOR dem Stripping,
    das Stripping selbst bleibt Sache des jeweiligen Aufrufers. Gilt nur für
    den Fall ``len(text) > chunk_size``; den Kurztext-Sonderfall behandelt
    jeder Aufrufer selbst.

    Issue #1347: Der Folgechunk-Start wird vor dem Wort-Snap an den Anfang
    seiner Zeile ausgerichtet, wenn diese Zeilengrenze innerhalb eines
    festen, begrenzten Rückblicks (``_LINE_SNAP_MIN_LOOKBACK``) liegt. Sonst
    zerschneidet die Fenstergrenze mehrzeilige Aussagen (Pfeil-Listen,
    Aufzählungen): Der Folgechunk enthält dann nur noch das letzte Fragment —
    die tragende Bedingung blieb im Vorchunk und die Faktenextraktion des
    Fragments erzeugt Evidence-False-Negatives. Der Zeilen-Snap ist
    verlustfrei (der Start wandert nur rückwärts) und auf die Rückblickweite
    begrenzt, damit Fließtextabsätze als eine lange Zeile nicht die
    Chunkgröße sprengen.
    """
    windows: List[Tuple[int, int]] = []
    start = 0

    while start < len(text):
        end = start + chunk_size

        # Try to split at sentence boundaries
        if end < len(text):
            # Find nearest sentence ending
            for sep in ['。', '！', '？', '.\n', '!\n', '?\n', '\n\n', '. ', '! ', '? ']:
                last_sep = text[start:end].rfind(sep)
                if last_sep != -1 and last_sep > chunk_size * 0.3:
                    end = start + last_sep + len(sep)
                    break

        windows.append((start, end))

        if end >= len(text):
            break

        # Folgechunk startet mit ``overlap`` Zeichen Kontext und wird
        # rückwärts auf einen Wortanfang gesnappt — so entstehen keine
        # 'uß-…'/'atische…'-Chunkanfänge mehr, ohne dass Text zwischen
        # ``end`` und dem neuen Start verloren geht. ``lower_bound`` ist die
        # Terminierungsgarantie: der neue Start ist immer strikt größer als
        # der alte, auch wenn die Satzgrenzen-Logik ``end`` so weit nach vorn
        # zieht, dass ``end - overlap <= start`` gilt (bei
        # ``overlap > 0.3 * chunk_size`` möglich).
        #
        # ``min_progress`` verhindert zusätzlich ein Degenerieren auf
        # Ein-Zeichen-Schritte: zieht die Satzgrenzen-Logik ``end`` weit nach
        # vorn und ist der Overlap groß, kann ``end - overlap`` hinter
        # ``start`` liegen. Ohne Mindestfortschritt entstünden dann tausende
        # fast identischer Chunks statt einer sinnvollen Aufteilung.
        min_progress = max(1, (end - start) // 2)
        next_start = max(end - overlap, start + min_progress)

        # Issue #1347: erst Zeilenalignment versuchen; scheitert es (keine
        # Zeilengrenze im Rückblick), greift der bisherige Wort-Snap.
        line_start = _snap_to_line_start(
            text,
            next_start,
            lookback_limit=_LINE_SNAP_MIN_LOOKBACK,
            lower_bound=start + 1,
        )
        if line_start is not None:
            start = line_start
        else:
            start = _snap_to_word_start(
                text,
                next_start,
                lower_bound=start + 1,
                upper_bound=end,
            )

    return windows


def split_text_into_chunks(
    text: str,
    chunk_size: int = 500,
    overlap: int = 50
) -> List[str]:
    """
    Split text into chunks.

    Chunks werden bevorzugt an einer Satzgrenze (``.``, ``?``, ``!``,
    ``。``, ``！``, ``？``, ``\\n\\n``) beendet, wenn eine solche im hinteren
    Drittel des Fensters liegt. Der Folgechunk startet an der
    ``end - overlap``-Position und wird von dort rückwärts auf einen
    Wortanfang gesnappt, damit kein Chunk mitten in einem Wort beginnt
    (verhindert Defekt-Truncation in Embedding-/GraphRAG-Pipelines, in denen
    solche Fragmente unsinnige Embeddings produzieren). Liegt eine
    Zeilengrenze im begrenzten Rückblick (Issue #1347), startet der
    Folgechunk stattdessen am Anfang seiner Zeile — mehrzeilige Aussagen
    (Pfeil-Listen, Aufzählungen) bleiben so im Folgechunk zusammen, statt als
    kontextloses Fragment zu enden. Beide Snaps sind verlustfrei — siehe
    :func:`_snap_to_word_start` und :func:`_snap_to_line_start`. Einzige
    Ausnahme: ein Wort, das länger als ``chunk_size`` ist, muss zwangsläufig
    aufgetrennt werden.

    Args:
        text: Original text
        chunk_size: Characters per chunk
        overlap: Overlapping characters

    Returns:
        List of text chunks
    """
    if len(text) <= chunk_size:
        return [text] if text.strip() else []

    chunks = []
    for start, end in _chunk_windows(text, chunk_size, overlap):
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)

    return chunks


def _assign_document(
    start: int,
    end: int,
    documents: List[DocumentManifestEntry],
    next_chunk_id: dict,
) -> Tuple[Optional[str], Optional[int]]:
    """Ordnet ein Chunk-Intervall ``[start, end)`` einem Manifest-Dokument zu.

    Gewinner ist das Dokument mit dem größten Zeichen-Overlap zwischen dem
    Chunk-Intervall und dem Dokument-Intervall (``[doc.start_offset,
    doc.end_offset)``) — so entscheidet bei einem grenzüberspannenden Chunk
    der größere Textanteil (ADR-0013 Slice 1, Teil A). Ohne Treffer im
    Manifest: ``(None, None)``, es wird nicht geraten.

    ``chunk_id`` ist ein pro ``document_id`` laufender Zähler, der bei 0
    beginnt — er läuft dokumentintern, nicht über das gesamte Manifest.
    """
    best_document_id: Optional[str] = None
    best_overlap = 0
    for doc in documents:
        overlap_len = min(end, doc.end_offset) - max(start, doc.start_offset)
        if overlap_len > best_overlap:
            best_overlap = overlap_len
            best_document_id = doc.document_id

    if best_document_id is None:
        return None, None

    chunk_id = next_chunk_id.get(best_document_id, 0)
    next_chunk_id[best_document_id] = chunk_id + 1
    return best_document_id, chunk_id


def split_text_into_chunks_with_documents(
    text: str,
    manifest: Optional[DocumentManifest] = None,
    chunk_size: int = 500,
    overlap: int = 50,
) -> List[DocumentAnchoredChunk]:
    """
    Wie ``split_text_into_chunks``, liefert zusätzlich Blob-Offsets und je
    Chunk eine Dokument-Zuordnung anhand von ``manifest`` (ADR-0013 Slice 1,
    Teil A, Issue #1152). ``split_text_into_chunks`` selbst bleibt
    unverändert (auch intern nur um :func:`_chunk_windows` erweitert, deren
    Fenster-Logik 1:1 aus der alten Implementierung übernommen ist) — andere
    Aufrufer sind von dieser Erweiterung nicht betroffen.

    Ein Chunk, der eine Dokumentgrenze überspannt, wird dem Dokument
    zugeordnet, in dem sein größter Textanteil liegt (siehe
    :func:`_assign_document`). Ohne Manifest (oder ohne Treffer im Manifest,
    etwa bei Altprojekten ohne Sidecar) sind ``document_id``/``chunk_id``
    ``None`` — geraten wird nicht.

    Args:
        text: Original text (z. B. der ``extracted_text.txt``-Blob).
        manifest: Dokument-Manifest mit Blob-Offsets, oder ``None``.
        chunk_size: Characters per chunk.
        overlap: Overlapping characters.

    Returns:
        Liste von ``DocumentAnchoredChunk``.
    """
    documents = manifest.documents if manifest is not None else []
    next_chunk_id: dict = {}

    if len(text) <= chunk_size:
        windows = [(0, len(text))] if text.strip() else []
        strip_windows = False
    else:
        windows = _chunk_windows(text, chunk_size, overlap)
        strip_windows = True

    result: List[DocumentAnchoredChunk] = []
    for start, end in windows:
        raw = text[start:end]
        if strip_windows:
            stripped = raw.strip()
            if not stripped:
                continue
            lstrip_len = len(raw) - len(raw.lstrip())
            actual_start = start + lstrip_len
            actual_end = actual_start + len(stripped)
            chunk_text = stripped
        else:
            # Kurztext-Sonderfall: split_text_into_chunks() gibt hier den
            # unveränderten Originaltext zurück (kein .strip()) — dieselbe
            # Semantik gilt hier für Konsistenz mit der Textform.
            chunk_text = raw
            actual_start = start
            actual_end = end

        document_id, chunk_id = _assign_document(actual_start, actual_end, documents, next_chunk_id)
        result.append(
            DocumentAnchoredChunk(
                text=chunk_text,
                start_offset=actual_start,
                end_offset=actual_end,
                document_id=document_id,
                chunk_id=chunk_id,
            )
        )

    return result


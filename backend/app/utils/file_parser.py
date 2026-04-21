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
  ENABLE_PDF_VISION=true|false           (default: true)
  VISION_MODEL_NAME=<ollama model>       (default: gemini-3-flash-preview:cloud)
  VISION_MIN_IMAGE_AREA=<px²>            (default: 40000 — ignore logos/icons)
  VISION_PAGE_SCAN_THRESHOLD=<chars>     (default: 100 — <=N chars triggers full-page render)
  VISION_MAX_DIM=<px>                    (default: 1400 — downscale longer side before encoding)
"""

import base64
import io
import os
from pathlib import Path
from typing import List, Optional


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
    except Exception:
        pass

    # Fall back to chardet
    if not encoding:
        try:
            import chardet
            result = chardet.detect(data)
            encoding = result.get('encoding') if result else None
        except Exception:
            pass

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
    except Exception:
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
    except Exception:
        pass
    # Fallback: let PyMuPDF re-encode
    try:
        import fitz
        pix = fitz.Pixmap(image_bytes)
        if pix.alpha:
            pix = fitz.Pixmap(fitz.csRGB, pix)
        return pix.tobytes('png')
    except Exception:
        return image_bytes  # last resort — hope the vision model copes


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
    except Exception:
        return image_bytes


class _VisionHelper:
    """Lazy wrapper around LLMClient.describe_image — survives missing Pillow etc."""

    def __init__(self):
        self.enabled = False
        self.model: Optional[str] = None
        self.client = None
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
        except Exception as exc:
            _log(f"vision disabled ({exc})")

    def describe(self, image_bytes: bytes, prompt: str, tag: str = "") -> str:
        if not self.enabled or not image_bytes:
            return ""
        try:
            png = _downscale_png(image_bytes, self.max_dim)
            b64 = base64.b64encode(png).decode('ascii')
            text = self.client.describe_image(b64, prompt=prompt, mime="image/png")
            return (text or '').strip()
        except Exception as exc:
            _log(f"vision call failed [{tag}]: {exc}")
            return ""


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

        enable_vision = os.environ.get('ENABLE_PDF_VISION', 'true').strip().lower() not in ('0', 'false', 'no', 'off')
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
                        except Exception as exc:
                            _log(f"vision page {idx} failed: {exc}")
                    else:
                        # Describe each substantial embedded image.
                        try:
                            images = page.get_images(full=True)
                        except Exception:
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
                            except Exception as exc:
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

        Args:
            file_paths: List of file paths

        Returns:
            Merged text
        """
        all_texts = []

        for i, file_path in enumerate(file_paths, 1):
            try:
                text = cls.extract_text(file_path)
                filename = Path(file_path).name
                all_texts.append(f"=== Document {i}: {filename} ===\n{text}")
            except Exception as e:
                all_texts.append(f"=== Document {i}: {file_path} (extraction failed: {str(e)}) ===")

        return "\n\n".join(all_texts)


def split_text_into_chunks(
    text: str,
    chunk_size: int = 500,
    overlap: int = 50
) -> List[str]:
    """
    Split text into chunks

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

        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)

        # Next chunk starts at overlap position
        start = end - overlap if end < len(text) else len(text)

    return chunks


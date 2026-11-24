"""Extract readable text from stored PDF and DOCX contract files.

Safety rules:
* The stored file is only ever read, never modified.
* File type is re-checked from the file's own bytes, not just its name.
* Size, page, and character limits bound memory and processing time.
* DOCX XML is parsed with the standard library after rejecting DOCTYPE and
  ENTITY declarations (no entity expansion or external references).
* Scanned/image-only PDFs have no text layer. OCR is NOT supported, so they
  are reported as having no extractable text instead of being guessed at.
"""

import logging
import re
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass
from pathlib import Path

from pypdf import PdfReader

from app.services.documents import DOCX_MIME, MAX_UPLOAD_BYTES, PDF_MIME

# pypdf logs warnings that can quote document fragments; keep them out.
logging.getLogger("pypdf").setLevel(logging.CRITICAL)

MAX_PDF_PAGES = 300
MAX_EXTRACTED_CHARS = 500_000
# Less than this many non-space characters counts as "no text layer".
MIN_TEXT_CHARS = 50
MAX_DOCX_XML_BYTES = 50 * 1024 * 1024

_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


class TextExtractionError(Exception):
    """Base class; ``message`` is safe to show to users."""

    code = "extraction_failed"
    message = "The document text could not be read."

    def __init__(self, message: str | None = None) -> None:
        super().__init__(message or self.message)
        if message:
            self.message = message


class UnreadableDocumentError(TextExtractionError):
    code = "unreadable_document"
    message = (
        "The stored document could not be read. It may be corrupted, "
        "encrypted, or not a valid PDF or Word file."
    )


class NoExtractableTextError(TextExtractionError):
    code = "no_extractable_text"
    message = (
        "No readable text was found in this document. It may be a scanned "
        "or image-only file. OCR is not supported, so it cannot be reviewed "
        "by AI. Upload a text-based PDF or a Word (.docx) version."
    )


@dataclass(frozen=True)
class ExtractedText:
    text: str
    method: str  # "pdf-text" or "docx-xml"
    pages: int | None
    truncated: bool  # True if extraction stopped at a safety limit


def _clean(raw: str) -> str:
    text = raw.replace("\x00", "")
    text = re.sub(r"[\x01-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)
    text = re.sub(r"[ \t ]+", " ", text)
    text = re.sub(r" ?\n ?", "\n", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _extract_pdf(path: Path) -> ExtractedText:
    try:
        reader = PdfReader(str(path))
        if reader.is_encrypted and not reader.decrypt(""):
            raise UnreadableDocumentError()

        pages = len(reader.pages)
        chunks: list[str] = []
        total = 0
        truncated = pages > MAX_PDF_PAGES

        for page in list(reader.pages)[:MAX_PDF_PAGES]:
            chunk = page.extract_text() or ""
            chunks.append(chunk)
            total += len(chunk)
            if total > MAX_EXTRACTED_CHARS:
                truncated = True
                break
    except TextExtractionError:
        raise
    except Exception:  # pypdf raises many types for malformed files
        raise UnreadableDocumentError() from None

    return ExtractedText(
        text=_clean("\n\n".join(chunks)),
        method="pdf-text",
        pages=pages,
        truncated=truncated,
    )


def _extract_docx(path: Path) -> ExtractedText:
    try:
        with zipfile.ZipFile(path) as archive:
            info = archive.getinfo("word/document.xml")
            if info.file_size > MAX_DOCX_XML_BYTES:
                raise UnreadableDocumentError()
            xml_bytes = archive.read(info)
    except TextExtractionError:
        raise
    except (zipfile.BadZipFile, KeyError, OSError, ValueError, RuntimeError):
        raise UnreadableDocumentError() from None

    head = xml_bytes[:4096].upper()
    if b"<!DOCTYPE" in head or b"<!ENTITY" in xml_bytes.upper():
        raise UnreadableDocumentError()

    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        raise UnreadableDocumentError() from None

    paragraphs: list[str] = []
    total = 0
    truncated = False

    for paragraph in root.iter(f"{_W}p"):
        parts: list[str] = []
        for node in paragraph.iter():
            if node.tag == f"{_W}t":
                parts.append(node.text or "")
            elif node.tag == f"{_W}tab":
                parts.append("\t")
            elif node.tag in (f"{_W}br", f"{_W}cr"):
                parts.append("\n")
        line = "".join(parts)
        paragraphs.append(line)
        total += len(line)
        if total > MAX_EXTRACTED_CHARS:
            truncated = True
            break

    return ExtractedText(
        text=_clean("\n".join(paragraphs)),
        method="docx-xml",
        pages=None,
        truncated=truncated,
    )


def extract_text(path: Path, mime_type: str) -> ExtractedText:
    """Extract text from a stored PDF or DOCX, or raise ``TextExtractionError``."""
    try:
        size = path.stat().st_size
        with open(path, "rb") as handle:
            signature = handle.read(5)
    except OSError:
        raise UnreadableDocumentError() from None

    if size > MAX_UPLOAD_BYTES:
        raise UnreadableDocumentError(
            "The stored document is larger than the 10 MB limit."
        )

    if mime_type == PDF_MIME and signature.startswith(b"%PDF-"):
        result = _extract_pdf(path)
    elif mime_type == DOCX_MIME and signature.startswith(b"PK\x03\x04"):
        result = _extract_docx(path)
    else:
        raise UnreadableDocumentError()

    if len(re.sub(r"\s+", "", result.text)) < MIN_TEXT_CHARS:
        raise NoExtractableTextError()
    return result

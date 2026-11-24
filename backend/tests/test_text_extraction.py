"""Text extraction from stored PDF and DOCX files (no database needed)."""

import hashlib
import io
import zipfile

import pytest
from helpers import (
    SAMPLE_CLAUSE_TEXT,
    make_blank_pdf,
    make_docx_with_text,
    make_text_pdf,
)

from app.services import text_extraction
from app.services.documents import DOCX_MIME, PDF_MIME
from app.services.text_extraction import (
    NoExtractableTextError,
    UnreadableDocumentError,
    extract_text,
)


def write(tmp_path, name, content: bytes):
    path = tmp_path / name
    path.write_bytes(content)
    return path


def test_extracts_text_from_pdf(tmp_path):
    path = write(tmp_path, "a.pdf", make_text_pdf())

    result = extract_text(path, PDF_MIME)

    assert result.method == "pdf-text"
    assert result.pages == 1
    assert result.truncated is False
    assert "thirty days of invoice" in " ".join(result.text.split())
    assert "governed by the laws of India" in " ".join(result.text.split())


def test_extracts_text_from_docx_including_tables(tmp_path):
    path = write(
        tmp_path,
        "a.docx",
        make_docx_with_text(
            "First paragraph about payment.",
            "Second paragraph about termination rights.",
            table_cells=("Cell one", "Cell two"),
        ),
    )

    result = extract_text(path, DOCX_MIME)

    assert result.method == "docx-xml"
    assert result.pages is None
    for expected in (
        "First paragraph about payment.",
        "Second paragraph about termination rights.",
        "Cell one",
        "Cell two",
    ):
        assert expected in result.text


def test_scanned_pdf_without_text_is_reported_honestly(tmp_path):
    path = write(tmp_path, "scan.pdf", make_blank_pdf())

    with pytest.raises(NoExtractableTextError) as excinfo:
        extract_text(path, PDF_MIME)

    assert "OCR is not supported" in excinfo.value.message


def test_docx_with_no_text_is_rejected(tmp_path):
    path = write(tmp_path, "empty.docx", make_docx_with_text(" "))

    with pytest.raises(NoExtractableTextError):
        extract_text(path, DOCX_MIME)


def test_short_text_counts_as_no_text(tmp_path):
    path = write(tmp_path, "tiny.docx", make_docx_with_text("Hi"))

    with pytest.raises(NoExtractableTextError):
        extract_text(path, DOCX_MIME)


@pytest.mark.parametrize(
    ("name", "content", "mime"),
    [
        ("garbage.pdf", b"%PDF-1.4 this is not really a pdf", PDF_MIME),
        ("notpdf.pdf", b"plain text", PDF_MIME),
        ("notzip.docx", b"plain text", DOCX_MIME),
        ("badzip.docx", b"PK\x03\x04 not a zip", DOCX_MIME),
        # A real PDF stored under a DOCX type (and vice versa).
        ("mismatch1.docx", make_text_pdf(), DOCX_MIME),
        ("mismatch2.pdf", make_docx_with_text(), PDF_MIME),
        ("unknown.bin", make_text_pdf(), "application/zip"),
    ],
)
def test_invalid_documents_are_rejected(tmp_path, name, content, mime):
    path = write(tmp_path, name, content)

    with pytest.raises(UnreadableDocumentError):
        extract_text(path, mime)


def test_missing_file_is_unreadable(tmp_path):
    with pytest.raises(UnreadableDocumentError):
        extract_text(tmp_path / "gone.pdf", PDF_MIME)


def test_docx_without_word_document_part_is_rejected(tmp_path):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("readme.txt", "just a zip")
    path = write(tmp_path, "nodoc.docx", buffer.getvalue())

    with pytest.raises(UnreadableDocumentError):
        extract_text(path, DOCX_MIME)


def test_docx_with_entity_declarations_is_rejected(tmp_path):
    ns = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    xml = (
        '<?xml version="1.0"?><!DOCTYPE d [<!ENTITY x "boom">]>'
        f'<w:document xmlns:w="{ns}"><w:body><w:p><w:r><w:t>&x;</w:t></w:r>'
        "</w:p></w:body></w:document>"
    )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("word/document.xml", xml)
    path = write(tmp_path, "entity.docx", buffer.getvalue())

    with pytest.raises(UnreadableDocumentError):
        extract_text(path, DOCX_MIME)


def test_extraction_stops_at_the_character_limit(tmp_path, monkeypatch):
    monkeypatch.setattr(text_extraction, "MAX_EXTRACTED_CHARS", 200)
    paragraphs = [f"Paragraph number {i} with enough words." for i in range(50)]
    path = write(tmp_path, "long.docx", make_docx_with_text(*paragraphs))

    result = extract_text(path, DOCX_MIME)

    assert result.truncated is True
    assert len(result.text) < 400


def test_extraction_never_modifies_the_original_file(tmp_path):
    for name, content, mime in (
        ("a.pdf", make_text_pdf(), PDF_MIME),
        ("a.docx", make_docx_with_text(), DOCX_MIME),
    ):
        path = write(tmp_path, name, content)
        before = hashlib.sha256(path.read_bytes()).hexdigest()
        mtime = path.stat().st_mtime_ns

        extract_text(path, mime)

        assert hashlib.sha256(path.read_bytes()).hexdigest() == before
        assert path.stat().st_mtime_ns == mtime


def test_sample_text_helper_has_enough_text():
    # Guards the other tests: the shared sample must pass the minimum.
    assert len(SAMPLE_CLAUSE_TEXT.replace(" ", "")) > text_extraction.MIN_TEXT_CHARS

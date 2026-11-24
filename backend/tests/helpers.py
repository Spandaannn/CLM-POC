"""Shared test helpers for document and AI-review tests.

Everything here is synthetic: no real contract text, no credentials.
"""

import io
import json
import zipfile

from app.core.cookies import CSRF_HEADER_NAME
from app.services.documents import DOCX_MIME, PDF_MIME

TEST_PASSWORD = "Pytest-Password-123!"

SAMPLE_CLAUSE_TEXT = (
    "Services Agreement between Acme Supplies Pvt Ltd and Northwind Traders. "
    "The Customer shall pay the Supplier a fee of INR 500,000 within thirty "
    "days of invoice. Either party may terminate this Agreement on ninety "
    "days written notice. The Supplier's total liability shall not exceed "
    "the fees paid in the preceding twelve months. This Agreement is "
    "governed by the laws of India."
)


def _pdf_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def make_text_pdf(text: str = SAMPLE_CLAUSE_TEXT) -> bytes:
    """Build a small valid PDF whose text layer contains ``text``."""
    words = text.split()
    lines, current = [], ""
    for word in words:
        if len(current) + len(word) + 1 > 80:
            lines.append(current)
            current = word
        else:
            current = f"{current} {word}".strip()
    lines.append(current)

    commands = ["BT", "/F1 11 Tf", "72 740 Td", "14 TL"]
    for line in lines:
        commands.append(f"({_pdf_escape(line)}) Tj T*")
    commands.append("ET")
    stream = "\n".join(commands).encode("latin-1", "replace")

    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Contents 5 0 R /Resources << /Font << /F1 4 0 R >> >> >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n"
        + stream
        + b"\nendstream",
    ]

    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n".encode()
    out += b"0000000000 65535 f \n"
    for offset in offsets:
        out += f"{offset:010d} 00000 n \n".encode()
    out += (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
        f"startxref\n{xref}\n%%EOF\n"
    ).encode()
    return bytes(out)


def make_blank_pdf() -> bytes:
    """A valid PDF with one page and no text (like a scanned document)."""
    from pypdf import PdfWriter

    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def make_docx_with_text(*paragraphs: str, table_cells: tuple[str, ...] = ()) -> bytes:
    """Build a valid .docx. Paragraphs and optional table cells hold the text."""
    ns = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    body = "".join(
        f"<w:p><w:r><w:t xml:space=\"preserve\">{p}</w:t></w:r></w:p>"
        for p in (paragraphs or (SAMPLE_CLAUSE_TEXT,))
    )
    if table_cells:
        cells = "".join(
            f"<w:tc><w:p><w:r><w:t>{c}</w:t></w:r></w:p></w:tc>"
            for c in table_cells
        )
        body += f"<w:tbl><w:tr>{cells}</w:tr></w:tbl>"
    document = f'<?xml version="1.0"?><w:document xmlns:w="{ns}"><w:body>{body}</w:body></w:document>'

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "[Content_Types].xml",
            '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>',
        )
        archive.writestr("word/document.xml", document)
    return buffer.getvalue()


def login(client, email: str) -> str:
    csrf = client.get("/api/auth/csrf").json()["csrf_token"]
    response = client.post(
        "/api/auth/login",
        json={"email": email, "password": TEST_PASSWORD},
        headers={CSRF_HEADER_NAME: csrf},
    )
    assert response.status_code == 200, response.text
    return response.json()["csrf_token"]


def create_contract(client, csrf: str) -> str:
    response = client.post(
        "/api/contracts",
        json={
            "title": "AI review test contract",
            "contract_type": "Services",
            "counterparty_name": "Example Corp",
        },
        headers={CSRF_HEADER_NAME: csrf},
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def upload_pdf(client, csrf, contract_id, content=None, name="agreement.pdf"):
    return client.post(
        f"/api/contracts/{contract_id}/documents",
        files={
            "file": (
                name,
                make_text_pdf() if content is None else content,
                PDF_MIME,
            )
        },
        headers={CSRF_HEADER_NAME: csrf},
    )


def upload_docx(client, csrf, contract_id, content=None, name="agreement.docx"):
    return client.post(
        f"/api/contracts/{contract_id}/documents",
        files={
            "file": (
                name,
                make_docx_with_text() if content is None else content,
                DOCX_MIME,
            )
        },
        headers={CSRF_HEADER_NAME: csrf},
    )


def ai_reply(**overrides) -> str:
    """A valid AI reply (as the provider would return it) as JSON text."""
    reply = {
        "summary": {
            "overview": "A services agreement between Acme Supplies and Northwind.",
            "parties": ["Acme Supplies Pvt Ltd", "Northwind Traders"],
            "commercial_terms": "Fee of INR 500,000 payable within thirty days.",
            "key_dates_and_obligations": "Termination on ninety days notice.",
        },
        "metadata": {
            "parties": ["Acme Supplies Pvt Ltd", "Northwind Traders"],
            "effective_date": None,
            "expiry_date": "not found",
            "contract_value": "500,000",
            "currency": "INR",
            "governing_law": "India",
            "renewal_terms": None,
        },
        "clauses": [
            {
                "category": "payment_terms",
                "title": "Payment",
                "summary": "Fee payable within thirty days of invoice.",
                "excerpt": "shall pay the Supplier a fee of INR 500,000 within thirty days of invoice",
            }
        ],
        "risk_findings": [
            {
                "title": "Low liability cap",
                "description": "Liability is capped at twelve months of fees.",
                "severity": "medium",
                "category": "limitation_of_liability",
                "excerpt": "total liability shall not exceed the fees paid in the preceding twelve months",
                "concern": "The cap may be too low for serious breaches.",
                "suggested_action": "Ask whether a higher cap is needed.",
            },
            {
                "title": "No data protection clause",
                "description": "The contract does not address personal data.",
                "severity": "high",
                "category": "data_protection",
                "excerpt": None,
                "concern": "Personal data handling is unregulated.",
                "suggested_action": "Add data protection terms.",
            },
        ],
        "playbook_results": [
            {
                "rule_id": "payment_terms",
                "status": "met",
                "explanation": "Amount and due date are stated.",
                "excerpt": "within thirty days of invoice",
            },
            {
                "rule_id": "governing_law",
                "status": "met",
                "explanation": "Indian law governs.",
                "excerpt": "governed by the laws of India",
            },
            {
                "rule_id": "data_protection",
                "status": "not_met",
                "explanation": "No data protection terms found.",
                "excerpt": None,
            },
        ],
    }
    reply.update(overrides)
    return json.dumps(reply)

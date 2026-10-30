from dataclasses import replace
from io import BytesIO
from pathlib import Path

from pypdf import PageObject, PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from backend.app.api.routes import documents as document_routes
from backend.tests.conftest import ApiClient


def _add_page_with_text(writer: PdfWriter, text: str | None) -> None:
    page = PageObject.create_blank_page(width=612, height=792)
    if text:
        font = DictionaryObject(
            {
                NameObject("/Type"): NameObject("/Font"),
                NameObject("/Subtype"): NameObject("/Type1"),
                NameObject("/BaseFont"): NameObject("/Helvetica"),
            }
        )
        page[NameObject("/Resources")] = DictionaryObject(
            {NameObject("/Font"): DictionaryObject({NameObject("/F1"): font})}
        )
        escaped = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        stream = DecodedStreamObject()
        stream.set_data(f"BT /F1 12 Tf 72 720 Td ({escaped}) Tj ET".encode("latin-1"))
        page[NameObject("/Contents")] = writer._add_object(stream)
    writer.add_page(page)


def make_pdf_with_pages(page_texts: list[str | None]) -> bytes:
    buffer = BytesIO()
    writer = PdfWriter()
    for text in page_texts:
        _add_page_with_text(writer, text)
    writer.write(buffer)
    return buffer.getvalue()


def configure_storage(monkeypatch, storage_root: Path) -> None:
    monkeypatch.setattr(
        document_routes,
        "settings",
        replace(document_routes.settings, storage_root=storage_root),
    )


def test_parse_multi_page_pdf_with_text_and_empty_page(
    client: ApiClient,
    monkeypatch,
    tmp_path: Path,
) -> None:
    configure_storage(monkeypatch, tmp_path)
    pdf_bytes = make_pdf_with_pages(
        [
            "Transformer architecture with self-attention",
            None,
            "Experimental results on WMT 2014 translation",
        ]
    )

    upload_resp = client.post(
        "/api/v1/documents/upload",
        data={"title": "Attention Paper"},
        files={"file": ("attention.pdf", pdf_bytes, "application/pdf")},
    )
    assert upload_resp.status_code == 201
    doc_id = upload_resp.json()["id"]

    parse_resp = client.post(f"/api/v1/documents/{doc_id}/parse")
    assert parse_resp.status_code == 200
    parsed = parse_resp.json()
    assert parsed["document"]["status"] == "ready"
    assert parsed["document"]["parsed_at"] is not None
    assert parsed["document"]["parse_error"] is None
    assert parsed["total_pages"] == 3
    assert parsed["non_empty_pages"] == 2
    assert parsed["empty_pages"] == 1
    assert parsed["failed_pages"] == 0
    assert parsed["total_chars"] > 0

    pages_resp = client.get(f"/api/v1/documents/{doc_id}/pages")
    assert pages_resp.status_code == 200
    pages_payload = pages_resp.json()
    assert pages_payload["document_status"] == "ready"
    assert pages_payload["total_pages"] == 3
    items = pages_payload["items"]
    assert [item["page_number"] for item in items] == [1, 2, 3]
    assert items[0]["status"] == "ready"
    assert "Transformer architecture" in items[0]["text"]
    assert items[1]["status"] == "empty"
    assert items[1]["char_count"] == 0
    assert items[2]["status"] == "ready"
    assert "WMT 2014" in items[2]["text"]


def test_parse_scanned_pdf_without_text_marks_failed(
    client: ApiClient,
    monkeypatch,
    tmp_path: Path,
) -> None:
    configure_storage(monkeypatch, tmp_path)
    blank_pdf = make_pdf_with_pages([None, None])

    upload_resp = client.post(
        "/api/v1/documents/upload",
        data={"title": "Scanned Paper"},
        files={"file": ("scanned.pdf", blank_pdf, "application/pdf")},
    )
    assert upload_resp.status_code == 201
    doc_id = upload_resp.json()["id"]

    parse_resp = client.post(f"/api/v1/documents/{doc_id}/parse")
    assert parse_resp.status_code == 200
    parsed = parse_resp.json()
    assert parsed["document"]["status"] == "failed"
    assert parsed["document"]["parse_error"] is not None
    assert "OCR" in parsed["document"]["parse_error"]
    assert parsed["total_pages"] == 2
    assert parsed["non_empty_pages"] == 0
    assert parsed["empty_pages"] == 2


def test_reparse_is_idempotent(
    client: ApiClient,
    monkeypatch,
    tmp_path: Path,
) -> None:
    configure_storage(monkeypatch, tmp_path)
    pdf_bytes = make_pdf_with_pages(["Page one content", "Page two content"])

    upload_resp = client.post(
        "/api/v1/documents/upload",
        files={"file": ("reparse.pdf", pdf_bytes, "application/pdf")},
    )
    doc_id = upload_resp.json()["id"]

    first_parse = client.post(f"/api/v1/documents/{doc_id}/parse")
    second_parse = client.post(f"/api/v1/documents/{doc_id}/parse")
    assert first_parse.status_code == 200
    assert second_parse.status_code == 200

    pages_resp = client.get(f"/api/v1/documents/{doc_id}/pages")
    assert pages_resp.json()["total_pages"] == 2
    assert len(pages_resp.json()["items"]) == 2


def test_reupload_soft_deleted_pdf_restores_document(
    client: ApiClient,
    monkeypatch,
    tmp_path: Path,
) -> None:
    configure_storage(monkeypatch, tmp_path)
    pdf_bytes = make_pdf_with_pages(["Restorable paper text"])

    first_upload = client.post(
        "/api/v1/documents/upload",
        data={"title": "Original Title"},
        files={"file": ("paper.pdf", pdf_bytes, "application/pdf")},
    )
    assert first_upload.status_code == 201
    doc_id = first_upload.json()["id"]

    client.post(f"/api/v1/documents/{doc_id}/parse")
    delete_resp = client.delete(f"/api/v1/documents/{doc_id}")
    assert delete_resp.status_code == 204

    second_upload = client.post(
        "/api/v1/documents/upload",
        data={"title": "Restored Title"},
        files={"file": ("paper-v2.pdf", pdf_bytes, "application/pdf")},
    )
    assert second_upload.status_code == 201
    restored = second_upload.json()
    assert restored["id"] == doc_id
    assert restored["title"] == "Restored Title"
    assert restored["status"] == "uploaded"
    assert restored["parsed_at"] is None

    pages_after_restore = client.get(f"/api/v1/documents/{doc_id}/pages")
    assert pages_after_restore.json()["total_pages"] == 0


def test_parse_document_without_stored_file_returns_404(client: ApiClient) -> None:
    create_resp = client.post(
        "/api/v1/documents",
        json={"title": "Metadata Only Document"},
    )
    assert create_resp.status_code == 201
    doc_id = create_resp.json()["id"]

    parse_resp = client.post(f"/api/v1/documents/{doc_id}/parse")
    assert parse_resp.status_code == 404
    assert "no stored file" in parse_resp.json()["detail"].lower()


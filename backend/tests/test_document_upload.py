from dataclasses import replace
from io import BytesIO
from pathlib import Path

from pypdf import PdfWriter

from backend.app.api.routes import documents as document_routes
from backend.tests.conftest import ApiClient


def make_pdf() -> bytes:
    buffer = BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    writer.write(buffer)
    return buffer.getvalue()


def configure_storage(monkeypatch, storage_root: Path, *, max_size_bytes: int = 1024 * 1024):
    monkeypatch.setattr(
        document_routes,
        "settings",
        replace(
            document_routes.settings,
            storage_root=storage_root,
            max_pdf_size_bytes=max_size_bytes,
        ),
    )


def test_upload_pdf_creates_blob_and_document(client: ApiClient, monkeypatch, tmp_path) -> None:
    configure_storage(monkeypatch, tmp_path)
    pdf_content = make_pdf()

    response = client.post(
        "/api/v1/documents/upload",
        data={"title": "Uploaded research paper"},
        files={"file": ("../research-paper.pdf", pdf_content, "application/pdf")},
    )

    assert response.status_code == 201
    document = response.json()
    assert document["title"] == "Uploaded research paper"
    assert document["original_filename"] == "research-paper.pdf"
    assert document["mime_type"] == "application/pdf"
    assert document["file_size"] == len(pdf_content)
    assert document["page_count"] == 1
    assert len(document["sha256"]) == 64
    assert document["storage_key"].startswith("blobs/")
    assert (tmp_path / document["storage_key"]).read_bytes() == pdf_content

    file_response = client.get(f"/api/v1/documents/{document['id']}/file")
    assert file_response.status_code == 200
    assert file_response.headers["content-type"] == "application/pdf"
    assert file_response.headers["content-disposition"].startswith("inline;")
    assert file_response.headers["x-frame-options"] == "SAMEORIGIN"
    assert file_response.content == pdf_content


def test_upload_rejects_duplicate_pdf(client: ApiClient, monkeypatch, tmp_path) -> None:
    configure_storage(monkeypatch, tmp_path)
    files = {"file": ("paper.pdf", make_pdf(), "application/pdf")}

    first_response = client.post("/api/v1/documents/upload", files=files)
    second_response = client.post("/api/v1/documents/upload", files=files)

    assert first_response.status_code == 201
    assert second_response.status_code == 409
    assert "already exists" in second_response.json()["detail"]
    assert len(list((tmp_path / "blobs").rglob("*.pdf"))) == 1


def test_upload_rejects_invalid_pdf(client: ApiClient, monkeypatch, tmp_path) -> None:
    configure_storage(monkeypatch, tmp_path)

    response = client.post(
        "/api/v1/documents/upload",
        files={"file": ("not-a-pdf.pdf", b"plain text", "application/pdf")},
    )

    assert response.status_code == 415
    assert not list(tmp_path.rglob("*.pdf"))


def test_upload_rejects_oversized_pdf(client: ApiClient, monkeypatch, tmp_path) -> None:
    configure_storage(monkeypatch, tmp_path, max_size_bytes=128)

    response = client.post(
        "/api/v1/documents/upload",
        files={"file": ("large.pdf", make_pdf(), "application/pdf")},
    )

    assert response.status_code == 413
    assert not list(tmp_path.rglob("*.pdf"))

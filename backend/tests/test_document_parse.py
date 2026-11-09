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



def test_parse_extracts_keywords_and_chunks_and_supports_search(
    client: ApiClient,
    monkeypatch,
    tmp_path: Path,
) -> None:
    configure_storage(monkeypatch, tmp_path)
    pdf_bytes = make_pdf_with_pages(
        [
            "Transformer Architecture and Self-Attention mechanism for neural translation.",
            "FastAPI and PostgreSQL backend pipeline with RAG chunking.",
        ]
    )

    upload_resp = client.post(
        "/api/v1/documents/upload",
        data={"title": "Transformer RAG Pipeline"},
        files={"file": ("transformer-rag.pdf", pdf_bytes, "application/pdf")},
    )
    assert upload_resp.status_code == 201
    doc_id = upload_resp.json()["id"]

    parse_resp = client.post(f"/api/v1/documents/{doc_id}/parse")
    assert parse_resp.status_code == 200
    parsed = parse_resp.json()
    assert len(parsed["keywords"]) >= 2
    assert parsed["total_chunks"] >= 2
    assert parsed["text_chunks"] >= 2

    chunks_resp = client.get(f"/api/v1/documents/{doc_id}/chunks")
    assert chunks_resp.status_code == 200
    chunks_data = chunks_resp.json()
    assert chunks_data["total_chunks"] == parsed["total_chunks"]
    assert len(chunks_data["items"]) >= 2

    search_resp = client.get(
        "/api/v1/documents/search",
        params={"q": "FastAPI PostgreSQL", "document_id": doc_id},
    )
    assert search_resp.status_code == 200
    search_data = search_resp.json()
    assert search_data["total"] >= 1
    assert search_data["items"][0]["chunk"]["page_number"] == 2
    assert "FastAPI" in search_data["items"][0]["matched_keywords"]


def test_table_key_value_binding_and_sparse_table_filtering() -> None:
    from backend.app.services.document_chunker import (
        clean_page_paragraphs,
        extract_table_chunks_for_page,
    )

    class DummyPlumberPage:
        def extract_tables(self):
            return [
                [
                    ["阶段", "建议时间", "核心内容"],
                    ["第一阶段", "第1-30天", "Python 与 FastAPI 基础"],
                    ["第二阶段", "第31-60天", "RAG 与 Tool Calling"],
                ],
                [
                    ["", None, "", None],
                    [None, "x", "", None],
                ],
            ]

    chunks, terms = extract_table_chunks_for_page(
        DummyPlumberPage(),
        page_number=2,
        start_index=0,
    )
    assert len(chunks) == 1
    table_chunk = chunks[0]
    assert table_chunk.chunk_type.value == "table"
    expected_row = "阶段: 第一阶段 | 建议时间: 第1-30天 | 核心内容: Python 与 FastAPI 基础"
    assert expected_row in table_chunk.content
    assert table_chunk.meta["headers"] == ["阶段", "建议时间", "核心内容"]
    assert table_chunk.meta["row_count"] == 2
    assert "FastAPI" in " ".join(terms)

    sample_raw = "This is a trans-\nformer model.\n\n1. Introduction\nWe propose RAG."
    paragraphs = clean_page_paragraphs(sample_raw)
    assert "This is a transformer model." in paragraphs[0]


def test_v04_embeddings_and_hybrid_bilingual_semantic_search(
    client: ApiClient,
    monkeypatch,
    tmp_path: Path,
) -> None:
    configure_storage(monkeypatch, tmp_path)
    pdf_bytes = make_pdf_with_pages(
        [
            "Self-attention mechanism reduces sequential computation complexity and parallelizes.",
            "Adam optimizer with warmup learning rate schedule and dropout during model training.",
        ]
    )

    upload_resp = client.post(
        "/api/v1/documents/upload",
        data={"title": "Bilingual Semantic Test"},
        files={"file": ("semantic.pdf", pdf_bytes, "application/pdf")},
    )
    assert upload_resp.status_code == 201
    doc_id = upload_resp.json()["id"]

    parse_resp = client.post(f"/api/v1/documents/{doc_id}/parse")
    assert parse_resp.status_code == 200
    parsed = parse_resp.json()
    assert parsed["embedded_chunks"] == parsed["total_chunks"]
    assert parsed["embedded_chunks"] >= 2
    assert parsed["embedding_model"] is not None

    chunks_resp = client.get(f"/api/v1/documents/{doc_id}/chunks")
    assert chunks_resp.status_code == 200
    chunks_payload = chunks_resp.json()
    assert chunks_payload["embedded_chunks"] >= 2
    assert all(item["has_embedding"] for item in chunks_payload["items"])

    # Cross-lingual semantic query in Chinese matching English text on Page 1
    sem_resp = client.get(
        "/api/v1/documents/search",
        params={
            "q": "自注意力机制与并行计算复杂度",
            "document_id": doc_id,
            "mode": "hybrid",
        },
    )
    assert sem_resp.status_code == 200
    sem_data = sem_resp.json()
    assert sem_data["mode"] == "hybrid"
    assert sem_data["total"] >= 1
    top_hit = sem_data["items"][0]
    assert top_hit["chunk"]["page_number"] == 1
    assert top_hit["semantic_score"] > 0.2


def test_ai_providers_json_config_endpoint(client: ApiClient) -> None:
    resp = client.get("/api/v1/documents/ai-config")
    assert resp.status_code == 200
    data = resp.json()
    assert data["embedding_dimensions"] == 256
    assert "local_bilingual" in data["available_embedding_providers"]
    assert "deepseek" in data["available_llm_providers"]



def test_v04_rag_grounded_qa_with_citations(
    client: ApiClient,
    monkeypatch,
    tmp_path: Path,
) -> None:
    configure_storage(monkeypatch, tmp_path)
    pdf_bytes = make_pdf_with_pages(
        [
            "Encoder and decoder stack consists of 6 identical layers.",
            "BLEU score on WMT 2014 English-to-German translation reaches 28.4.",
        ]
    )

    upload_resp = client.post(
        "/api/v1/documents/upload",
        data={"title": "Attention BLEU Report"},
        files={"file": ("bleu.pdf", pdf_bytes, "application/pdf")},
    )
    assert upload_resp.status_code == 201
    doc_id = upload_resp.json()["id"]
    client.post(f"/api/v1/documents/{doc_id}/parse")

    ask_resp = client.post(
        f"/api/v1/documents/{doc_id}/ask",
        json={
            "question": "WMT 2014 翻译实验的 BLEU 分数是多少？",
            "mode": "hybrid",
            "top_k": 3,
        },
    )
    assert ask_resp.status_code == 200
    data = ask_resp.json()
    assert "[1]" in data["answer"]
    assert len(data["citations"]) >= 1
    assert data["citations"][0]["citation_index"] == 1
    assert data["citations"][0]["page_number"] == 2
    assert "28.4" in data["citations"][0]["snippet"]

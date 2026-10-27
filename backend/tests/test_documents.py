from backend.tests.conftest import ApiClient


def test_document_crud_lifecycle(client: ApiClient) -> None:
    create_response = client.post(
        "/api/v1/documents",
        json={
            "title": "Attention Is All You Need",
            "original_filename": "attention.pdf",
            "mime_type": "application/pdf",
            "file_size": 1024,
            "sha256": "a" * 64,
            "storage_key": "blobs/attention.pdf",
        },
    )
    assert create_response.status_code == 201
    created = create_response.json()
    document_id = created["id"]
    assert created["status"] == "uploaded"

    list_response = client.get("/api/v1/documents")
    assert list_response.status_code == 200
    assert list_response.json()["total"] == 1

    get_response = client.get(f"/api/v1/documents/{document_id}")
    assert get_response.status_code == 200
    assert get_response.json()["title"] == "Attention Is All You Need"

    update_response = client.patch(
        f"/api/v1/documents/{document_id}",
        json={"title": "Transformer Paper", "status": "ready"},
    )
    assert update_response.status_code == 200
    assert update_response.json()["title"] == "Transformer Paper"
    assert update_response.json()["status"] == "ready"

    delete_response = client.delete(f"/api/v1/documents/{document_id}")
    assert delete_response.status_code == 204

    missing_response = client.get(f"/api/v1/documents/{document_id}")
    assert missing_response.status_code == 404
    assert client.get("/api/v1/documents").json()["total"] == 0


def test_duplicate_document_is_rejected(client: ApiClient) -> None:
    payload = {"title": "First", "sha256": "b" * 64}

    assert client.post("/api/v1/documents", json=payload).status_code == 201
    duplicate_response = client.post(
        "/api/v1/documents",
        json={"title": "Duplicate", "sha256": "b" * 64},
    )

    assert duplicate_response.status_code == 409


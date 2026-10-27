from backend.tests.conftest import ApiClient


def test_service_info(client: ApiClient) -> None:
    response = client.get("/")

    assert response.status_code == 200
    payload = response.json()
    assert payload["name"] == "AI Research Hub API"
    assert payload["version"] == "0.1.0"
    assert payload["docs_url"].endswith("/docs")
    assert response.headers["x-content-type-options"] == "nosniff"


def test_health_check(client: ApiClient) -> None:
    response = client.get("/api/v1/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["environment"] == "development"


def test_readiness_check(client: ApiClient) -> None:
    response = client.get("/api/v1/ready")

    assert response.status_code == 200
    assert response.json()["database"] == "ok"

from fastapi.testclient import TestClient

from app.main import create_app


def test_health():
    with TestClient(create_app()) as client:
        response = client.get("/health")
        assert response.status_code == 200
        body = response.json()
        assert {k: body[k] for k in ("status", "service", "stage")} == {
            "status": "ok",
            "service": "resolva-api",
            "stage": "scaffold",
        }
        assert "/health" in client.get("/openapi.json").json()["paths"]

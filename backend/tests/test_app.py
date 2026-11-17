from fastapi.testclient import TestClient

from app.main import create_app


def client(settings):
    return TestClient(create_app(settings))


def test_health_reports_mode_and_trace_header(settings):
    response = client(settings).get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["mode"] == "ai_assisted" and body["llm_provider"] == "mock"
    assert response.headers["X-Trace-Id"]


def test_health_rules_only_when_ai_disabled(settings):
    off = settings.model_copy(update={"ai_enabled": False})
    assert client(off).get("/health").json()["mode"] == "rules_only"


def test_incoming_trace_id_is_propagated(settings):
    response = client(settings).get("/health", headers={"X-Trace-Id": "abc123"})
    assert response.headers["X-Trace-Id"] == "abc123"


def test_errors_are_problem_json(settings):
    response = client(settings).get("/nope")
    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["status"] == 404 and response.json()["trace_id"]


def test_openapi_available(settings):
    assert client(settings).get("/openapi.json").status_code == 200


def test_health_reuses_one_provider(settings):
    app = create_app(settings)
    with TestClient(app) as c:
        c.get("/health")
        first = app.state.provider
        c.get("/health")
        assert app.state.provider is first


def test_health_reports_unavailable_groq_without_key(settings):
    groq = settings.model_copy(update={"llm_provider": "groq", "groq_api_key": None})
    body = client(groq).get("/health").json()
    assert body["llm_status"] == "unavailable" and body["mode"] == "rules_only"


def test_health_reports_unreachable_ollama(settings):
    down = settings.model_copy(
        update={"llm_provider": "ollama", "ollama_base_url": "http://127.0.0.1:9"}
    )
    body = client(down).get("/health").json()
    assert body["llm_status"] == "unreachable" and body["mode"] == "rules_only"

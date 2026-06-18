from __future__ import annotations

from fastapi.testclient import TestClient

from product_agent.api.fastapi_app import create_app


def test_runtime_config_api_returns_masked_status(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-api-route-secret")
    app = create_app()
    client = TestClient(app)

    response = client.get("/config/runtime")

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["data"]["llm_available"] is True
    assert "sk-api-route-secret" not in response.text

from __future__ import annotations

from product_agent.schemas import UpdateRuntimeApiKeyRequest
from product_agent.services.runtime_config_service import RuntimeConfigService


def test_runtime_config_writes_and_masks_api_key(tmp_path, monkeypatch) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text("PRODUCT_AGENT_STORAGE=sqlite\n", encoding="utf-8")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    service = RuntimeConfigService(env_path=env_path)

    status = service.update_api_key(
        UpdateRuntimeApiKeyRequest(
            provider="openai",
            action="set",
            api_key="sk-test-runtime-config-secret",
        )
    )

    openai_status = next(item for item in status.api_keys if item.provider == "openai")
    assert openai_status.configured is True
    assert openai_status.source == ".env"
    assert openai_status.fingerprint.startswith("sha256:")
    assert "sk-test-runtime-config-secret" not in status.model_dump_json()
    assert "PRODUCT_AGENT_STORAGE=sqlite" in env_path.read_text(encoding="utf-8")
    assert "OPENAI_API_KEY=sk-test-runtime-config-secret" in env_path.read_text(encoding="utf-8")


def test_runtime_config_clears_api_key(tmp_path, monkeypatch) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text("OPENAI_API_KEY=sk-old\nDEEPSEEK_API_KEY=sk-deepseek\n", encoding="utf-8")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-old")
    service = RuntimeConfigService(env_path=env_path)

    status = service.update_api_key(
        UpdateRuntimeApiKeyRequest(provider="openai", action="clear")
    )

    openai_status = next(item for item in status.api_keys if item.provider == "openai")
    assert openai_status.configured is False
    assert "OPENAI_API_KEY=" in env_path.read_text(encoding="utf-8")
    assert "DEEPSEEK_API_KEY=sk-deepseek" in env_path.read_text(encoding="utf-8")

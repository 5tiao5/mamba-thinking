from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass
from pathlib import Path

from product_agent.schemas import (
    RuntimeApiKeyStatusView,
    RuntimeConfigStatusResponse,
    RuntimeFlagView,
    UpdateRuntimeApiKeyRequest,
)
from product_agent.services.paper_brief_llm_service import paper_brief_llm_enabled


class RuntimeConfigError(ValueError):
    pass


@dataclass(frozen=True)
class _ApiKeySpec:
    provider: str
    env_key: str
    label: str
    help_text: str


_API_KEY_SPECS = {
    "openai": _ApiKeySpec(
        provider="openai",
        env_key="OPENAI_API_KEY",
        label="OpenAI API Key",
        help_text="用于 OpenAI 兼容模型调用，优先级高于 DeepSeek。",
    ),
    "deepseek": _ApiKeySpec(
        provider="deepseek",
        env_key="DEEPSEEK_API_KEY",
        label="DeepSeek API Key",
        help_text="OpenAI key 未配置时作为默认 LLM provider。",
    ),
    "s2": _ApiKeySpec(
        provider="s2",
        env_key="S2_API_KEY",
        label="Semantic Scholar API Key",
        help_text="提高 Semantic Scholar 检索/引用元数据额度；非 LLM key。",
    ),
}

_RUNTIME_FLAGS = (
    (
        "PAPER_BRIEF_LLM_MODE",
        "论文详情 LLM 模式",
        "auto",
        "auto/on/off；默认 auto，有 LLM key 时增强高优先级论文详情。",
    ),
    (
        "PAPER_BRIEF_LLM_MAX_PER_WORKSPACE",
        "每轮增强论文上限",
        "4",
        "限制每个 workspace 交给 LLM 编辑的论文数量，防止慢和烧额度。",
    ),
    (
        "WORKSPACE_PAPER_BRIEF_WORKERS",
        "论文详情并行 worker",
        "4",
        "构建论文卡片时的线程数上限。",
    ),
    (
        "ENABLE_WORKSPACE_PAPER_PARALLEL",
        "强制并行论文卡片",
        "auto",
        "设为 1 可在未启用 Paper Brief LLM 时也并行构建论文卡片。",
    ),
    (
        "SKIP_PAPER_BRIEF_LLM",
        "跳过论文详情 LLM",
        "0",
        "设为 1 时关闭 Paper Brief LLM 编辑层。",
    ),
    (
        "SKIP_RESEARCH_BRIEF_LLM",
        "跳过研究简报 LLM",
        "0",
        "设为 1 时研究简报只使用确定性模板。",
    ),
)


class RuntimeConfigService:
    def __init__(self, env_path: Path | None = None) -> None:
        self.env_path = env_path or Path(__file__).resolve().parents[1] / ".env"

    def get_status(self) -> RuntimeConfigStatusResponse:
        env_file_values = self._read_env_file_values()
        openai_configured = bool(os.environ.get("OPENAI_API_KEY", "").strip())
        deepseek_configured = bool(os.environ.get("DEEPSEEK_API_KEY", "").strip())
        active_provider = "openai" if openai_configured else ("deepseek" if deepseek_configured else "none")
        default_model = ""
        if active_provider == "openai":
            default_model = os.environ.get("OPENAI_MODEL", "gpt-4.1-mini")
        elif active_provider == "deepseek":
            default_model = os.environ.get("DEEPSEEK_MODEL", "deepseek-chat")

        return RuntimeConfigStatusResponse(
            env_file_path=str(self.env_path),
            env_file_exists=self.env_path.exists(),
            active_provider=active_provider,
            default_model=default_model,
            llm_available=openai_configured or deepseek_configured,
            paper_brief_llm_enabled=paper_brief_llm_enabled(),
            research_brief_llm_enabled=(
                (openai_configured or deepseek_configured)
                and os.environ.get("SKIP_RESEARCH_BRIEF_LLM") != "1"
            ),
            semantic_scholar_available=bool(os.environ.get("S2_API_KEY", "").strip()),
            api_keys=[
                self._api_key_status(spec, env_file_values)
                for spec in _API_KEY_SPECS.values()
            ],
            runtime_flags=[
                RuntimeFlagView(
                    key=key,
                    label=label,
                    value=os.environ.get(key, ""),
                    effective_value=os.environ.get(key, default),
                    description=description,
                )
                for key, label, default, description in _RUNTIME_FLAGS
            ],
            safety_notes=[
                "完整 API key 不会返回给前端；页面只展示是否配置、来源和短指纹。",
                "保存 key 会写入项目根目录 .env，并同步当前后端进程环境变量。",
                "如果外部 shell/系统环境变量覆盖 .env，重启后仍可能以外部环境为准。",
            ],
        )

    def update_api_key(self, request: UpdateRuntimeApiKeyRequest) -> RuntimeConfigStatusResponse:
        spec = _API_KEY_SPECS.get(request.provider)
        if spec is None:
            raise RuntimeConfigError("Unsupported API key provider.")

        if request.action == "clear":
            self._write_env_value(spec.env_key, "")
            os.environ.pop(spec.env_key, None)
            return self.get_status()

        value = request.api_key.strip()
        if not value:
            raise RuntimeConfigError("API key cannot be empty.")
        if self._looks_unsafe_env_value(value):
            raise RuntimeConfigError("API key contains unsupported characters.")
        self._write_env_value(spec.env_key, value)
        os.environ[spec.env_key] = value
        return self.get_status()

    def _api_key_status(self, spec: _ApiKeySpec, env_file_values: dict[str, str]) -> RuntimeApiKeyStatusView:
        value = os.environ.get(spec.env_key, "").strip()
        file_value = env_file_values.get(spec.env_key, "").strip()
        configured = bool(value)
        if not configured:
            source = "missing"
        elif file_value and file_value == value:
            source = ".env"
        elif file_value and file_value != value:
            source = "process_override"
        else:
            source = "process"
        return RuntimeApiKeyStatusView(
            provider=spec.provider,  # type: ignore[arg-type]
            env_key=spec.env_key,
            label=spec.label,
            configured=configured,
            source=source,
            fingerprint=self._fingerprint(value) if configured else "",
            help_text=spec.help_text,
        )

    def _read_env_file_values(self) -> dict[str, str]:
        values: dict[str, str] = {}
        if not self.env_path.exists():
            return values
        for raw_line in self.env_path.read_text(encoding="utf-8").splitlines():
            parsed = self._parse_env_line(raw_line)
            if parsed is None:
                continue
            key, value = parsed
            values[key] = value
        return values

    def _write_env_value(self, key: str, value: str) -> None:
        self.env_path.parent.mkdir(parents=True, exist_ok=True)
        lines = self.env_path.read_text(encoding="utf-8").splitlines() if self.env_path.exists() else []
        updated = False
        next_lines: list[str] = []
        pattern = re.compile(rf"^(\s*(?:export\s+)?{re.escape(key)}\s*=).*$")
        for line in lines:
            if pattern.match(line):
                next_lines.append(f"{key}={value}")
                updated = True
            else:
                next_lines.append(line)
        if not updated:
            if next_lines and next_lines[-1].strip():
                next_lines.append("")
            next_lines.append(f"{key}={value}")
        self.env_path.write_text("\n".join(next_lines).rstrip() + "\n", encoding="utf-8")

    @staticmethod
    def _parse_env_line(raw_line: str) -> tuple[str, str] | None:
        line = raw_line.strip()
        if not line or line.startswith("#"):
            return None
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        if "=" not in line:
            return None
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            return None
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        return key, value

    @staticmethod
    def _fingerprint(value: str) -> str:
        digest = hashlib.sha256(value.encode("utf-8")).hexdigest()
        return f"sha256:{digest[:10]}"

    @staticmethod
    def _looks_unsafe_env_value(value: str) -> bool:
        return any(char in value for char in "\r\n")

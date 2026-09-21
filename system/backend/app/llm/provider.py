from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from openai import APITimeoutError, OpenAI

from app.core.config import Settings, get_settings


class LLMConfigurationError(RuntimeError):
    """运行时模型配置缺失；消息固定且不包含凭据。"""


def is_timeout_exception(exc: BaseException) -> bool:
    """判定 LLM 调用异常是否属于超时。

    覆盖两类来源：服务层自身的截止时间（内置 ``TimeoutError``）与
    OpenAI 兼容客户端的提供方超时（``APITimeoutError``）。
    """

    return isinstance(exc, (TimeoutError, APITimeoutError))


@dataclass(frozen=True)
class LLMCompletion:
    content: str
    model: str
    usage: dict[str, int | None] = field(default_factory=dict)


class LLMProvider(Protocol):
    model_name: str
    router_model: str
    generation_model: str

    def complete(self, *, messages: list[dict[str, str]], timeout: float,
                 max_tokens: int, model: str | None = None,
                 json_mode: bool = False, thinking_enabled: bool = False) -> LLMCompletion: ...


class OpenAICompatibleLLMProvider:
    def __init__(self, settings: Settings | None = None):
        settings = settings or get_settings()
        if settings.llm_api_key is None or not settings.llm_api_key.get_secret_value().strip():
            raise LLMConfigurationError("LLM_API_KEY 尚未配置")
        self.router_model = settings.llm_router_model
        self.generation_model = settings.llm_generation_model
        self.model_name = self.generation_model
        self._client = OpenAI(
            api_key=settings.llm_api_key.get_secret_value(),
            base_url=settings.llm_base_url,
            timeout=settings.llm_timeout_seconds,
            max_retries=0,
        )

    def complete(self, *, messages: list[dict[str, str]], timeout: float,
                 max_tokens: int, model: str | None = None,
                 json_mode: bool = False, thinking_enabled: bool = False) -> LLMCompletion:
        selected_model = model or self.generation_model
        kwargs = {
            "model": selected_model,
            "messages": messages,
            "max_tokens": max_tokens,
            "timeout": timeout,
            "stream": False,
            "extra_body": {
                "thinking": {"type": "enabled" if thinking_enabled else "disabled"},
            },
        }
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        response = self._client.chat.completions.create(
            **kwargs,  # type: ignore[arg-type]
        )
        content = response.choices[0].message.content or ""
        usage = response.usage
        return LLMCompletion(
            content=content,
            model=response.model or selected_model,
            usage={
                "prompt_tokens": getattr(usage, "prompt_tokens", None),
                "completion_tokens": getattr(usage, "completion_tokens", None),
                "total_tokens": getattr(usage, "total_tokens", None),
            },
        )


def create_llm_provider(settings: Settings | None = None) -> LLMProvider:
    return OpenAICompatibleLLMProvider(settings)


__all__ = [
    "LLMCompletion", "LLMConfigurationError", "LLMProvider",
    "OpenAICompatibleLLMProvider", "create_llm_provider", "is_timeout_exception",
]

from __future__ import annotations

import importlib
import os
from typing import Any

from browser_ai_test.config import LLMConfig


class ModelConfigurationError(ValueError):
    """The configured Browser Use model cannot be constructed safely."""


_PROVIDER_CLASSES: dict[str, tuple[str, ...]] = {
    "browser_use": ("browser_use.ChatBrowserUse", "browser_use.llm.ChatBrowserUse"),
    "openai": ("browser_use.ChatOpenAI", "browser_use.llm.ChatOpenAI"),
    "openai_compatible": ("browser_use.ChatOpenAI", "browser_use.llm.ChatOpenAI"),
    "anthropic": ("browser_use.ChatAnthropic", "browser_use.llm.ChatAnthropic"),
    "google": ("browser_use.ChatGoogle", "browser_use.llm.ChatGoogle"),
}


def _import_class(path: str) -> type[Any]:
    module_name, separator, class_name = path.rpartition(".")
    if not separator:
        raise ModelConfigurationError(f"模型 class_path 必须是完整导入路径: {path!r}")
    try:
        value = getattr(importlib.import_module(module_name), class_name)
    except (ImportError, AttributeError) as exc:
        raise ModelConfigurationError(f"无法导入模型类 {path!r}: {exc}") from exc
    if not isinstance(value, type):
        raise ModelConfigurationError(f"模型 class_path 不是类: {path!r}")
    return value


def _resolve_model_class(config: LLMConfig) -> type[Any]:
    if config.provider == "custom":
        if not config.class_path:
            raise ModelConfigurationError("provider=custom 时必须配置 llm.class_path")
        return _import_class(config.class_path)

    failures: list[str] = []
    for path in _PROVIDER_CLASSES[config.provider]:
        try:
            return _import_class(path)
        except ModelConfigurationError as exc:
            failures.append(str(exc))
    raise ModelConfigurationError("；".join(failures))


def create_llm(config: LLMConfig) -> Any:
    """Create a browser-use native or arbitrary user-supplied model adapter.

    ``kwargs`` is applied first, then explicit portable fields override it. This lets
    custom adapters receive provider-specific options while keeping secrets in env.
    """
    model_class = _resolve_model_class(config)
    constructor_kwargs = dict(config.kwargs)
    if config.model is not None:
        constructor_kwargs["model"] = config.model
    if config.base_url is not None:
        constructor_kwargs["base_url"] = config.base_url
    if config.api_key_env:
        api_key = os.getenv(config.api_key_env)
        if not api_key:
            raise ModelConfigurationError(
                f"模型密钥环境变量 {config.api_key_env!r} 未设置或为空"
            )
        constructor_kwargs["api_key"] = api_key
    try:
        return model_class(**constructor_kwargs)
    except Exception as exc:
        raise ModelConfigurationError(
            f"模型 {model_class.__module__}.{model_class.__name__} 初始化失败: {exc}"
        ) from exc

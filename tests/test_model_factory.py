import sys
import types

import pytest

from browser_ai_test.agent.model_factory import ModelConfigurationError, create_llm
from browser_ai_test.config import LLMConfig


class FakeCustomModel:
    def __init__(self, **kwargs):
        self.options = kwargs


@pytest.fixture
def custom_model_module(monkeypatch):
    module = types.ModuleType("fake_custom_models")
    module.FakeCustomModel = FakeCustomModel
    monkeypatch.setitem(sys.modules, "fake_custom_models", module)


def test_custom_model_receives_portable_and_provider_options(custom_model_module, monkeypatch):
    monkeypatch.setenv("PRIVATE_MODEL_TOKEN", "secret-token")
    config = LLMConfig(
        provider="custom",
        class_path="fake_custom_models.FakeCustomModel",
        model="private-model-v2",
        base_url="http://model.internal/v1",
        api_key_env="PRIVATE_MODEL_TOKEN",
        kwargs={"temperature": 0, "custom_option": True},
    )

    model = create_llm(config)

    assert isinstance(model, FakeCustomModel)
    assert model.options == {
        "model": "private-model-v2",
        "base_url": "http://model.internal/v1",
        "api_key": "secret-token",
        "temperature": 0,
        "custom_option": True,
    }


def test_explicit_fields_override_kwargs(custom_model_module):
    config = LLMConfig(
        provider="custom",
        class_path="fake_custom_models.FakeCustomModel",
        model="configured-model",
        kwargs={"model": "ignored-model"},
    )
    assert create_llm(config).options["model"] == "configured-model"


def test_custom_provider_requires_class_path():
    with pytest.raises(ModelConfigurationError, match="class_path"):
        create_llm(LLMConfig(provider="custom"))


def test_missing_api_key_environment_variable_is_explicit(custom_model_module, monkeypatch):
    monkeypatch.delenv("MISSING_MODEL_TOKEN", raising=False)
    config = LLMConfig(
        provider="custom",
        class_path="fake_custom_models.FakeCustomModel",
        api_key_env="MISSING_MODEL_TOKEN",
    )
    with pytest.raises(ModelConfigurationError, match="MISSING_MODEL_TOKEN"):
        create_llm(config)


def test_invalid_custom_class_path_is_explicit():
    config = LLMConfig(provider="custom", class_path="does_not_exist.Adapter")
    with pytest.raises(ModelConfigurationError, match="无法导入"):
        create_llm(config)


def test_openai_compatible_uses_browser_use_native_adapter(monkeypatch):
    module = types.ModuleType("browser_use")
    module.ChatOpenAI = FakeCustomModel
    monkeypatch.setitem(sys.modules, "browser_use", module)
    config = LLMConfig(
        provider="openai_compatible",
        model="local-model",
        base_url="http://localhost:8000/v1",
    )

    model = create_llm(config)

    assert isinstance(model, FakeCustomModel)
    assert model.options == {
        "model": "local-model",
        "base_url": "http://localhost:8000/v1",
    }

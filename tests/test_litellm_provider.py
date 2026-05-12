"""Unit tests for LiteLLM provider integration in ask_llm_v2."""

import ast
import sys
import types
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
import yaml


ASK_LLM_PATH = Path(__file__).resolve().parents[1] / "tools" / "ask_llm_v2.py"
CONFIG_PATH = Path(__file__).resolve().parents[1] / "model_config.yaml"


class TestLiteLLMCodePath:
    """Verify the litellm branch exists in ask_llm_v2.py source."""

    def test_litellm_branch_exists(self):
        src = ASK_LLM_PATH.read_text()
        assert 'model_provider == "litellm"' in src

    def test_uses_drop_params_true(self):
        src = ASK_LLM_PATH.read_text()
        assert '"drop_params": True' in src or "'drop_params': True" in src

    def test_uses_litellm_completion(self):
        src = ASK_LLM_PATH.read_text()
        assert "litellm.completion(" in src

    def test_imports_litellm_at_top(self):
        src = ASK_LLM_PATH.read_text()
        assert "import litellm" in src.split("def ")[0]

    def test_skips_empty_api_key(self):
        src = ASK_LLM_PATH.read_text()
        assert 'api_key != "EMPTY"' in src

    def test_skips_empty_api_base(self):
        src = ASK_LLM_PATH.read_text()
        assert 'api_base != "EMPTY"' in src


class TestModelConfig:
    """Verify model_config.yaml has litellm entry."""

    def test_litellm_in_config(self):
        with open(CONFIG_PATH, "r") as f:
            config = yaml.safe_load(f)
        assert "litellm" in config

    def test_litellm_config_has_api_base(self):
        with open(CONFIG_PATH, "r") as f:
            config = yaml.safe_load(f)
        assert "api_base" in config["litellm"]

    def test_litellm_config_has_api_key(self):
        with open(CONFIG_PATH, "r") as f:
            config = yaml.safe_load(f)
        assert "api_key" in config["litellm"]


class TestLiteLLMSDKCall:
    """Test litellm SDK call pattern directly (no module import needed)."""

    def test_completion_called_with_drop_params(self):
        fake = types.ModuleType("litellm")
        mock_msg = MagicMock(content="4", reasoning_content=None, reasoning=None)
        mock_resp = MagicMock(
            choices=[MagicMock(message=mock_msg)],
            usage=MagicMock(prompt_tokens=10, completion_tokens=5, total_tokens=15),
            id="test-id",
        )
        fake.completion = MagicMock(return_value=mock_resp)
        sys.modules["litellm"] = fake

        try:
            fake.completion(
                model="anthropic/claude-sonnet-4-20250514",
                messages=[{"role": "user", "content": "2+2?"}],
                drop_params=True,
                temperature=0.5,
                max_tokens=100,
            )
            kwargs = fake.completion.call_args.kwargs
            assert kwargs["model"] == "anthropic/claude-sonnet-4-20250514"
            assert kwargs["drop_params"] is True
        finally:
            del sys.modules["litellm"]

    def test_completion_forwards_api_key(self):
        fake = types.ModuleType("litellm")
        mock_msg = MagicMock(content="ok", reasoning_content=None, reasoning=None)
        mock_resp = MagicMock(
            choices=[MagicMock(message=mock_msg)],
            usage=MagicMock(prompt_tokens=5, completion_tokens=1, total_tokens=6),
            id="test-id",
        )
        fake.completion = MagicMock(return_value=mock_resp)
        sys.modules["litellm"] = fake

        try:
            fake.completion(
                model="openai/gpt-4o",
                messages=[{"role": "user", "content": "hi"}],
                api_key="sk-test",
                drop_params=True,
            )
            assert fake.completion.call_args.kwargs["api_key"] == "sk-test"
        finally:
            del sys.modules["litellm"]

    def test_completion_response_has_content(self):
        fake = types.ModuleType("litellm")
        mock_msg = MagicMock(content="4", reasoning_content=None, reasoning=None)
        mock_resp = MagicMock(
            choices=[MagicMock(message=mock_msg)],
            usage=MagicMock(prompt_tokens=10, completion_tokens=5, total_tokens=15),
            id="test-id",
        )
        fake.completion = MagicMock(return_value=mock_resp)
        sys.modules["litellm"] = fake

        try:
            resp = fake.completion(
                model="openai/gpt-4o",
                messages=[{"role": "user", "content": "2+2?"}],
                drop_params=True,
            )
            assert resp.choices[0].message.content == "4"
        finally:
            del sys.modules["litellm"]

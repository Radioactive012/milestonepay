import pytest

from app.ai.contract import ClaudeContractAI, ContractAIError
from app.config import Settings


def test_missing_anthropic_key_gives_a_clear_error(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    ai = ClaudeContractAI(Settings(_env_file=None, anthropic_api_key=""))
    with pytest.raises(ContractAIError) as error:
        ai.analyse(text="Logo, USD 500", file_bytes=None, media_type=None)
    assert "ANTHROPIC_API_KEY" in str(error.value)


def test_unsupported_file_type_is_refused(monkeypatch):
    ai = ClaudeContractAI(Settings(_env_file=None, anthropic_api_key="test-key"))
    with pytest.raises(ContractAIError) as error:
        ai.analyse(text=None, file_bytes=b"abc", media_type="application/zip")
    assert "PDF" in str(error.value)

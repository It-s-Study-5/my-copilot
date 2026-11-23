import secrets
from pathlib import Path

import pytest

from code_impact.model import FakeModel, create_model
from code_impact.models import ModelError


def test_fake_fixed_response_and_recording() -> None:
    model = FakeModel("fixed")
    assert model.complete("system", "user") == "fixed"
    assert model.complete("system2", "user2") == "fixed"
    assert model.calls == [("system", "user"), ("system2", "user2")]


def test_fake_sequence() -> None:
    model = FakeModel(["first", "second"])
    assert model.complete("s", "u") == "first"
    assert model.complete("s", "u") == "second"
    with pytest.raises(ModelError):
        model.complete("s", "u")


def test_missing_settings(tmp_path: Path) -> None:
    with pytest.raises(ModelError) as error:
        create_model(tmp_path / ".env")
    assert error.value.code == "MODEL_ERROR"


def test_placeholder_is_not_a_provider(tmp_path: Path) -> None:
    path = tmp_path / ".env"
    path.write_text("CODE_IMPACT_MODEL_PROVIDER={모델 공급자}\nCODE_IMPACT_MODEL={모델명}\nCODE_IMPACT_API_KEY=\n", encoding="utf-8")
    with pytest.raises(ModelError):
        create_model(path)


def test_key_is_never_exposed(tmp_path: Path, caplog) -> None:
    key = secrets.token_urlsafe()
    path = tmp_path / ".env"
    path.write_text(f"CODE_IMPACT_MODEL_PROVIDER=unselected\nCODE_IMPACT_MODEL=unselected\nCODE_IMPACT_API_KEY={key}\n", encoding="utf-8")
    with pytest.raises(ModelError) as error:
        create_model(path)
    assert key not in str(error.value) and key not in caplog.text
    assert error.value.__cause__ is None


def test_process_environment_is_not_key_source(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("CODE_IMPACT_MODEL_PROVIDER", "unselected")
    monkeypatch.setenv("CODE_IMPACT_MODEL", "unselected")
    monkeypatch.setenv("CODE_IMPACT_API_KEY", secrets.token_urlsafe())
    with pytest.raises(ModelError, match=".env"):
        create_model(tmp_path / ".env")

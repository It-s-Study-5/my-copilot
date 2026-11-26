import secrets

import pytest

from code_impact.model import FakeModel, GeminiModel, OpenAIModel, create_model
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


def _env(provider: str, key: str = "test-key", model: str = "m-1") -> dict[str, str]:
    return {"CODE_IMPACT_MODEL_PROVIDER": provider, "CODE_IMPACT_MODEL": model, "CODE_IMPACT_API_KEY": key}


def test_missing_settings() -> None:
    with pytest.raises(ModelError) as error:
        create_model({})
    assert error.value.code == "MODEL_ERROR"


def test_blank_key_is_missing() -> None:
    with pytest.raises(ModelError, match="API 키"):
        create_model(_env("openai", key="  "))


def test_key_is_never_exposed(caplog) -> None:
    key = secrets.token_urlsafe()
    with pytest.raises(ModelError) as error:
        create_model(_env("unselected", key=key))
    assert key not in str(error.value) and key not in caplog.text
    assert error.value.__cause__ is None


def test_process_environment_is_key_source(monkeypatch) -> None:
    # 확장이 execFile의 env로 넘긴 값을 읽는다.
    for name, value in _env("openai", model="gpt-x").items():
        monkeypatch.setenv(name, value)
    model = create_model()
    assert isinstance(model, OpenAIModel) and model.model == "gpt-x"


# --- 공급자 adapter: 실제 API는 호출하지 않고 urlopen을 가짜로 바꿔 검증한다. ---
import io
import json
import urllib.error
import urllib.request



def _fake_urlopen(monkeypatch, response: object, sent: list) -> None:
    def urlopen(request, timeout):
        sent.append(request)
        if isinstance(response, Exception):
            raise response
        return io.BytesIO(json.dumps(response).encode())
    monkeypatch.setattr(urllib.request, "urlopen", urlopen)


@pytest.mark.parametrize(("provider", "cls"), [("gemini", GeminiModel), ("OpenAI", OpenAIModel)])
def test_provider_selects_adapter(provider: str, cls: type) -> None:
    model = create_model(_env(provider))
    assert isinstance(model, cls) and model.model == "m-1"


def test_unknown_provider() -> None:
    with pytest.raises(ModelError, match="gemini"):
        create_model(_env("nope"))


def test_gemini_request_and_response(monkeypatch) -> None:
    sent: list = []
    _fake_urlopen(monkeypatch, {"candidates": [{"content": {"parts": [{"text": '{"a"'}, {"text": ": 1}"}]}}]}, sent)
    assert GeminiModel("gemini-x", "k").complete("SYS", "USR") == '{"a": 1}'
    request = sent[0]
    body = json.loads(request.data)
    assert request.full_url.endswith("/models/gemini-x:generateContent") and "k" not in request.full_url
    assert request.get_header("X-goog-api-key") == "k"
    assert body["systemInstruction"]["parts"][0]["text"] == "SYS"
    assert body["contents"][0]["parts"][0]["text"] == "USR"
    assert body["generationConfig"]["responseMimeType"] == "application/json"


def test_openai_request_and_response(monkeypatch) -> None:
    sent: list = []
    _fake_urlopen(monkeypatch, {"choices": [{"message": {"content": '{"a": 1}'}}]}, sent)
    assert OpenAIModel("gpt-x", "k").complete("SYS", "USR") == '{"a": 1}'
    body = json.loads(sent[0].data)
    assert sent[0].get_header("Authorization") == "Bearer k"
    assert body["model"] == "gpt-x"
    assert body["messages"] == [{"role": "system", "content": "SYS"}, {"role": "user", "content": "USR"}]
    assert body["response_format"] == {"type": "json_object"}


@pytest.mark.parametrize("cls", [GeminiModel, OpenAIModel])
@pytest.mark.parametrize("response", [
    {"unexpected": True},
    urllib.error.HTTPError("https://x", 401, "Unauthorized", None, io.BytesIO(b"secret-key echoed")),
    urllib.error.URLError("down"),
    TimeoutError(),
])
def test_adapter_failures_hide_key(monkeypatch, cls: type, response: object) -> None:
    key = secrets.token_urlsafe()
    _fake_urlopen(monkeypatch, response, [])
    with pytest.raises(ModelError) as error:
        cls("m", key).complete("s", "u")
    assert key not in str(error.value) and "secret-key" not in str(error.value)
    assert error.value.__cause__ is None

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol

from dotenv import dotenv_values

from .models import ModelError

TIMEOUT = 60


class Model(Protocol):
    def complete(self, system: str, user: str) -> str:
        ...


def complete(system: str, user: str) -> str:
    return create_model().complete(system, user)


def create_model(env_file: str | Path | None = None) -> Model:
    # CODE_IMPACT_ENV_FILE: 테스트가 실제 .env(실제 API 키)를 읽지 않게 할 때 쓴다.
    default = os.environ.get("CODE_IMPACT_ENV_FILE") or Path(__file__).resolve().parents[1] / ".env"
    path = Path(env_file) if env_file is not None else Path(default)
    try:
        config = dotenv_values(path, interpolate=False)
    except (OSError, UnicodeError):
        raise ModelError("모델 설정 파일을 읽을 수 없습니다.") from None
    provider, model, key = (
        (config.get(name) or "").strip() for name in (
            "CODE_IMPACT_MODEL_PROVIDER", "CODE_IMPACT_MODEL", "CODE_IMPACT_API_KEY",
        )
    )
    if not all(value and "{" not in value for value in (provider, model, key)):
        raise ModelError(".env의 모델 공급자, 모델명, API 키 설정을 확인해야 합니다.")
    adapter = PROVIDERS.get(provider.lower())
    if adapter is None:
        raise ModelError(f"지원하지 않는 모델 공급자입니다. 사용 가능: {', '.join(PROVIDERS)}")
    return adapter(model, key)


def _post(url: str, headers: dict[str, str], body: dict[str, Any]) -> Any:
    # ponytail: SDK 대신 urllib 직접 호출. 스트리밍/도구 호출이 필요해지면 공급자 SDK로 교체.
    request = urllib.request.Request(
        url, data=json.dumps(body).encode(), method="POST",
        headers={"Content-Type": "application/json", **headers},
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            return json.loads(response.read())
    except urllib.error.HTTPError as error:
        # 응답 본문/헤더에 키나 요청 내용이 섞일 수 있어 상태 코드만 남긴다.
        raise ModelError(f"모델 API 호출에 실패했습니다(HTTP {error.code}).") from None
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        raise ModelError("모델 API에 연결할 수 없거나 응답을 읽을 수 없습니다.") from None


class GeminiModel:
    URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

    def __init__(self, model: str, key: str) -> None:
        self.model, self._key = model, key

    def complete(self, system: str, user: str) -> str:
        data = _post(
            self.URL.format(model=urllib.parse.quote(self.model, safe="")),
            {"x-goog-api-key": self._key},  # URL 쿼리 대신 헤더로 보내 키가 에러/로그에 남지 않게 한다.
            {
                "systemInstruction": {"parts": [{"text": system}]},
                "contents": [{"role": "user", "parts": [{"text": user}]}],
                "generationConfig": {"responseMimeType": "application/json"},
            },
        )
        try:
            return "".join(part["text"] for part in data["candidates"][0]["content"]["parts"] if "text" in part)
        except (KeyError, IndexError, TypeError):
            raise ModelError("Gemini 응답 형식이 올바르지 않습니다.") from None


class OpenAIModel:
    URL = "https://api.openai.com/v1/chat/completions"

    def __init__(self, model: str, key: str) -> None:
        self.model, self._key = model, key

    def complete(self, system: str, user: str) -> str:
        data = _post(
            self.URL,
            {"Authorization": f"Bearer {self._key}"},
            {
                "model": self.model,
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
                "response_format": {"type": "json_object"},
            },
        )
        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError):
            content = None
        if not isinstance(content, str):
            raise ModelError("OpenAI 응답 형식이 올바르지 않습니다.")
        return content


# 공급자 추가: complete(system, user) -> str 을 가진 클래스를 만들고 여기에 한 줄 등록한다.
PROVIDERS: dict[str, Callable[[str, str], Model]] = {"gemini": GeminiModel, "openai": OpenAIModel}


class FakeModel:
    def __init__(self, responses: str | list[str]) -> None:
        self.responses = [responses] if isinstance(responses, str) else list(responses)
        self.calls: list[tuple[str, str]] = []
        self._repeat = isinstance(responses, str)
        self._index = 0

    def complete(self, system: str, user: str) -> str:
        self.calls.append((system, user))
        if not self.responses or (not self._repeat and self._index >= len(self.responses)):
            raise ModelError("테스트 모델에 남은 응답이 없습니다.")
        response = self.responses[0 if self._repeat else self._index]
        self._index += 1
        return response

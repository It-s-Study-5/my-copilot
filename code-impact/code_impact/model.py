import json
import os
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping
from typing import Any, Protocol

from .models import ModelError

TIMEOUT = 60


class Model(Protocol):
    def complete(self, system: str, user: str) -> str:
        ...


def complete(system: str, user: str) -> str:
    return create_model().complete(system, user)


def create_model(env: Mapping[str, str] | None = None) -> Model:
    # VS Code 확장이 채팅에서 연결한 키와 선택한 모델을 환경변수로 넘겨준다.
    env = os.environ if env is None else env
    provider, model, key = (
        (env.get(name) or "").strip() for name in (
            "CODE_IMPACT_MODEL_PROVIDER", "CODE_IMPACT_MODEL", "CODE_IMPACT_API_KEY",
        )
    )
    if not all((provider, model, key)):
        raise ModelError("VS Code 채팅에서 OpenAI API 키를 연결해야 AI 분석을 할 수 있습니다.")
    adapter = PROVIDERS.get(provider.lower())
    if adapter is None:
        raise ModelError(f"지원하지 않는 모델 공급자입니다. 사용 가능: {', '.join(PROVIDERS)}")
    return adapter(model, key)


def _post(url: str, headers: dict[str, str], body: dict[str, Any]) -> Any:
    # SDK 대신 urllib 직접 호출. 스트리밍/도구 호출이 필요해지면 공급자 SDK로 교체.
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

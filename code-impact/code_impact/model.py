from pathlib import Path
from typing import Protocol

from dotenv import dotenv_values

from .models import ModelError


class Model(Protocol):
    def complete(self, system: str, user: str) -> str:
        ...


def complete(system: str, user: str) -> str:
    return create_model().complete(system, user)


def create_model(env_file: str | Path | None = None) -> Model:
    path = Path(env_file) if env_file is not None else Path(__file__).resolve().parents[1] / ".env"
    try:
        config = dotenv_values(path, interpolate=False)
    except (OSError, UnicodeError):
        raise ModelError("모델 설정 파일을 읽을 수 없습니다.") from None
    provider, model, key = (
        config.get(name) for name in (
            "CODE_IMPACT_MODEL_PROVIDER", "CODE_IMPACT_MODEL", "CODE_IMPACT_API_KEY",
        )
    )
    if not all(isinstance(value, str) and value.strip() and "{" not in value for value in (provider, model, key)):
        raise ModelError(".env의 모델 공급자, 모델명, API 키 설정을 확인해야 합니다.")
    # P5의 공급자/모델명이 미지정이라 실제 SDK 연결은 선택 후 구현한다.
    raise ModelError("선택한 모델 공급자 연결이 아직 구현되지 않았습니다.")


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

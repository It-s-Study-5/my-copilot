from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar, Literal

if TYPE_CHECKING:
    from tree_sitter import Node


class CodeImpactError(Exception):
    code: ClassVar[str]
    message: ClassVar[str]

    def __init__(self, message: str | None = None) -> None:
        super().__init__(message or self.message)


class NotInFunction(CodeImpactError):
    code = "NOT_IN_FUNCTION"
    message = "커서가 함수 안에 있지 않습니다."


class UnsupportedLanguage(CodeImpactError):
    code = "UNSUPPORTED_LANGUAGE"
    message = "지원하지 않는 파일 형식입니다."


class SourceNotFound(CodeImpactError):
    code = "FILE_NOT_FOUND"
    message = "파일 또는 프로젝트 루트를 읽을 수 없습니다."


class ModelError(CodeImpactError):
    code = "MODEL_ERROR"
    message = "모델 설정 또는 응답을 확인해야 합니다."


@dataclass
class Function:
    name: str
    file: str
    start_line: int
    end_line: int
    # 분석용 메타데이터는 formatter에서 외부 JSON에 포함하지 않는다.
    source: str = field(default="", kw_only=True, repr=False, compare=False)
    source_truncated: bool = field(default=False, kw_only=True, compare=False)
    path: Path | None = field(default=None, kw_only=True, repr=False, compare=False)
    node: Node | None = field(default=None, kw_only=True, repr=False, compare=False)


@dataclass
class CallSite:
    callee: str
    line: int
    col: int
    # callback = 호출하지 않고 함수 자체를 넘기는 위치 (인자, JSX 속성, .bind)
    kind: Literal["call", "callback"] = "call"


@dataclass
class ImpactNode(Function):
    depth: int
    calls: list[CallSite] = field(default_factory=list)
    facts: list[str] = field(default_factory=list)
    risk: str | None = None
    risk_level: Literal["high", "medium", "low"] | None = None

    @property
    def relation(self) -> Literal["direct", "indirect"]:
        return "direct" if self.depth == 1 else "indirect"


@dataclass
class AnalysisResult:
    target: Function
    summary: str | None = None
    impacts: list[ImpactNode] = field(default_factory=list)
    truncated: bool = False
    warnings: list[str] = field(default_factory=list)
    root: Path | None = field(default=None, kw_only=True, repr=False, compare=False)

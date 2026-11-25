from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .models import AnalysisResult, Function


def _positive(value: int) -> bool:
    return type(value) is int and value >= 1


def _strings(value: list[str]) -> bool:
    return isinstance(value, list) and all(isinstance(item, str) for item in value)


def _location(function: Function, root: Path | None) -> dict[str, Any]:
    if not isinstance(function.name, str) or not function.name:
        raise ValueError("함수명이 필요합니다.")
    if not isinstance(function.file, str) or not function.file:
        raise ValueError("함수 파일 경로가 필요합니다.")
    if not _positive(function.start_line) or not _positive(function.end_line) or function.end_line < function.start_line:
        raise ValueError("함수 줄 번호가 올바르지 않습니다.")
    path = Path(function.file)
    if root is not None:
        root = root.resolve()
        path = (path if path.is_absolute() else root / path).resolve()
        if not path.is_relative_to(root):
            raise ValueError("함수 파일은 프로젝트 루트 안에 있어야 합니다.")
        path = path.relative_to(root)
    if path.is_absolute() or ".." in path.parts or path.as_posix() == ".":
        raise ValueError("함수 파일은 root 기준 상대경로여야 합니다.")
    return {
        "name": function.name, "file": path.as_posix(),
        "start_line": function.start_line, "end_line": function.end_line,
    }


def to_json(result: AnalysisResult) -> str:
    if result.summary is not None and not isinstance(result.summary, str):
        raise ValueError("요약은 문자열 또는 null이어야 합니다.")
    if type(result.truncated) is not bool or not _strings(result.warnings):
        raise ValueError("탐색 상태 또는 경고 형식이 올바르지 않습니다.")
    if not isinstance(result.trace, list) or not all(isinstance(step, dict) for step in result.trace):
        raise ValueError("실행 기록 형식이 올바르지 않습니다.")
    if not isinstance(result.impacts, list):
        raise ValueError("영향 후보는 목록이어야 합니다.")
    target = _location(result.target, result.root)
    impacts: list[dict[str, Any]] = []
    modules: list[tuple[int, int, str | None]] = []
    levels = {"high": 0, "medium": 1, "low": 2, None: 3}
    for node in result.impacts:
        if not _positive(node.depth) or node.relation not in ("direct", "indirect") or node.relation != ("direct" if node.depth == 1 else "indirect"):
            raise ValueError("호출 깊이 또는 관계 값이 올바르지 않습니다.")
        if node.risk_level not in ("high", "medium", "low", None):
            raise ValueError("위험 수준이 올바르지 않습니다.")
        if node.risk is not None and not isinstance(node.risk, str):
            raise ValueError("위험 설명은 문자열 또는 null이어야 합니다.")
        if (node.risk is None) != (node.risk_level is None):
            raise ValueError("위험 설명과 위험 수준의 null 상태가 일치해야 합니다.")
        if node.name == "<module>":
            # 파일 최상위 호출은 risk만 모아 맨 아래에 보여준다.
            modules.append((levels[node.risk_level], node.depth, node.risk))
            continue
        location = _location(node, result.root)
        if not _strings(node.facts) or not isinstance(node.calls, list):
            raise ValueError("정적 근거 또는 호출 위치 형식이 올바르지 않습니다.")
        calls: list[dict[str, Any]] = []
        for call in node.calls:
            if not isinstance(call.callee, str) or not call.callee or not _positive(call.line) or not _positive(call.col):
                raise ValueError("호출 위치가 올바르지 않습니다.")
            if not node.start_line <= call.line <= node.end_line:
                raise ValueError("호출 위치가 호출 함수 밖에 있습니다.")
            if call.kind not in ("call", "callback"):
                raise ValueError("호출 종류가 올바르지 않습니다.")
            calls.append({"callee": call.callee, "line": call.line, "col": call.col, "kind": call.kind})
        impacts.append({
            **location, "depth": node.depth, "relation": node.relation,
            "calls": calls, "facts": list(node.facts),
            "risk": node.risk, "risk_level": node.risk_level,
        })
    impacts.sort(key=lambda node: (levels[node["risk_level"]], node["depth"]))
    if modules:
        risks = [risk for _, _, risk in sorted(modules, key=lambda item: item[:2]) if risk is not None]
        impacts.append({"name": "<module>", "risk": list(dict.fromkeys(risks))})
    return json.dumps({
        "target": target, "summary": result.summary, "impacts": impacts,
        "truncated": result.truncated, "warnings": list(result.warnings),
        "trace": list(result.trace),
    }, ensure_ascii=False, allow_nan=False)

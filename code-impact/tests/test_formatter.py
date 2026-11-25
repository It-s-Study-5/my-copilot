import json
from pathlib import Path

import pytest

from code_impact.formatter import to_json
from code_impact.models import AnalysisResult, CallSite, Function, ImpactNode


def make_result() -> AnalysisResult:
    return AnalysisResult(Function("target", "target.js", 1, 3), impacts=[
        ImpactNode("low", "a.js", 1, 3, 1, risk="검토할 수 있습니다.", risk_level="low"),
        ImpactNode("indirect", "b.js", 1, 3, 2, risk="확인해야 합니다.", risk_level="high"),
        ImpactNode("high", "c.js", 1, 3, 1, risk="확인해야 합니다.", risk_level="high"),
    ])


def test_sort_and_exact_schema() -> None:
    result = make_result()
    data = json.loads(to_json(result))
    assert [node["name"] for node in data["impacts"]] == ["high", "indirect", "low"]
    assert set(data) == {"target", "summary", "impacts", "truncated", "warnings"}
    assert set(data["target"]) == {"name", "file", "start_line", "end_line"}
    assert set(data["impacts"][0]) == {"name", "file", "start_line", "end_line", "depth", "relation", "calls", "facts", "risk", "risk_level"}
    assert result.impacts[0].name == "low"


def test_nullable_ai_and_relative_path(tmp_path: Path) -> None:
    result = AnalysisResult(Function("target", str(tmp_path / "target.js"), 1, 3), root=tmp_path)
    result.impacts.append(ImpactNode("caller", "caller.js", 1, 3, 1))
    data = json.loads(to_json(result))
    assert data["target"]["file"] == "target.js" and data["summary"] is None
    assert data["impacts"][0]["risk"] is None and data["impacts"][0]["risk_level"] is None


@pytest.mark.parametrize(("field", "value"), [
    ("depth", 0), ("depth", True), ("risk_level", "critical"),
    ("file", "../outside.js"), ("start_line", 0), ("facts", [123]),
    ("risk", None),
])
def test_invalid_values(field: str, value) -> None:
    result = make_result()
    setattr(result.impacts[0], field, value)
    with pytest.raises(ValueError):
        to_json(result)


def test_invalid_calls() -> None:
    result = make_result()
    result.impacts[0].calls = [CallSite("target", 1, 0)]
    with pytest.raises(ValueError):
        to_json(result)


def test_relation_tracks_depth() -> None:
    node = make_result().impacts[0]
    assert node.relation == "direct"
    node.depth = 2
    assert node.relation == "indirect"


def test_call_kind_is_output_and_validated() -> None:
    result = make_result()
    result.impacts[0].calls = [CallSite("target", 1, 1, "callback")]
    call = next(node for node in json.loads(to_json(result))["impacts"] if node["name"] == "low")["calls"][0]
    assert call == {"callee": "target", "line": 1, "col": 1, "kind": "callback"}
    result.impacts[0].calls = [CallSite("target", 1, 1, "render")]
    with pytest.raises(ValueError):
        to_json(result)


def test_module_risks_are_listed_last() -> None:
    result = make_result()
    result.impacts += [
        ImpactNode("<module>", "routes/a.js", 1, 3, 2, risk="라우터 a를 확인해야 합니다.", risk_level="low"),
        ImpactNode("<module>", "routes/b.js", 1, 3, 1, risk="라우터 b를 확인해야 합니다.", risk_level="high"),
        ImpactNode("<module>", "routes/c.js", 1, 3, 1),
    ]
    impacts = json.loads(to_json(result))["impacts"]
    assert [node["name"] for node in impacts] == ["high", "indirect", "low", "<module>"]
    assert impacts[-1] == {"name": "<module>", "risk": ["라우터 b를 확인해야 합니다.", "라우터 a를 확인해야 합니다."]}

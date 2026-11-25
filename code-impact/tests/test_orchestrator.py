import json
import secrets
from pathlib import Path

import pytest

from code_impact.model import FakeModel
from code_impact.models import SourceNotFound
from code_impact.orchestrator import MAX_TURNS, analyze


def response(**extra) -> str:
    return json.dumps({
        "impacts": [
            {"name": "createOrder", "file": "order.js", "risk": "금액 검증을 확인해야 합니다.", "risk_level": "high", "facts": ["모델이 지어낸 사실"]},
            {"name": "preparePayment", "file": "payment.js", "risk": "전달 결과에 영향을 줄 수 있습니다.", "risk_level": "low"},
            {"name": "handleOrderRequest", "file": "handler.js", "risk": "응답에 간접적인 영향 가능성이 있습니다.", "risk_level": "low"},
        ],
        "summary": "계산 결과가 주문 처리에 연결됩니다. 반환값 사용 방식을 확인해야 합니다.",
        **extra,
    }, ensure_ascii=False)


def run(fixtures_dir: Path, model: FakeModel):
    return analyze(fixtures_dir, fixtures_dir / "price.js", 2, 2, 3, model)


def test_facts_preserved_and_ai_matched(fixtures_dir: Path) -> None:
    model = FakeModel(response())
    result = run(fixtures_dir, model)
    assert result.summary and len(result.impacts) == 3 and not result.warnings
    order = next(node for node in result.impacts if node.name == "createOrder")
    assert order.risk_level == "high" and "확인해야" in order.risk
    assert "amount를 saveOrder()에 전달한다." in order.facts
    assert "모델이 지어낸 사실" not in order.facts
    payload = json.loads(model.calls[0][1])
    assert payload["target"]["source"].startswith("function calculatePrice")
    handler = next(node for node in payload["impacts"] if node["name"] == "handleOrderRequest")
    assert handler["call_paths"] == [["calculatePrice", "createOrder", "handleOrderRequest"]]
    assert "변경 내용은 주어지지 않았다" in model.calls[0][0]


def test_backticks_are_removed_from_ai_text(fixtures_dir: Path) -> None:
    data = json.loads(response())
    data["summary"] = "`calculatePrice()` 결과를 확인해야 합니다."
    data["impacts"][0]["risk"] = "`amount` 검증을 확인해야 합니다."
    result = run(fixtures_dir, FakeModel(json.dumps(data, ensure_ascii=False)))
    order = next(node for node in result.impacts if node.name == "createOrder")
    assert result.summary == "calculatePrice() 결과를 확인해야 합니다."
    assert order.risk == "amount 검증을 확인해야 합니다."


def test_invalid_json_twice_preserves_static_result(fixtures_dir: Path) -> None:
    model = FakeModel(["invalid", "invalid again"])
    result = run(fixtures_dir, model)
    assert len(model.calls) == 2 and result.summary is None and result.warnings
    assert len(result.impacts) == 3 and all(node.risk is None and node.risk_level is None for node in result.impacts)
    assert all(node.facts for node in result.impacts)


def test_retry_then_success(fixtures_dir: Path) -> None:
    model = FakeModel(["invalid", response()])
    result = run(fixtures_dir, model)
    assert len(model.calls) == 2 and result.summary and not result.warnings


def actions(*items: tuple[str, str]) -> str:
    return json.dumps({"actions": [
        {"tool": tool, "args": {"name": name}, "reason": f"{name} 확인이 필요하다."} for tool, name in items
    ]}, ensure_ascii=False)


def test_static_steps_and_answer_are_traced(fixtures_dir: Path) -> None:
    result = run(fixtures_dir, FakeModel(response()))
    assert [(step["actor"], step["tool"]) for step in result.trace] == [
        ("static", "find_callers"), ("static", "inspect_usage"), ("agent", "answer"),
    ]
    assert [step["step"] for step in result.trace] == [1, 2, 3]


def test_agent_reads_function_then_answers(fixtures_dir: Path) -> None:
    model = FakeModel([actions(("read_function", "createOrder")), response()])
    result = run(fixtures_dir, model)
    assert result.summary and len(model.calls) == 2 and not result.warnings
    second = json.loads(model.calls[1][1])
    assert second["observations"][0]["tool"] == "read_function"
    assert "saveOrder(amount)" in second["observations"][0]["result"][0]["source"]
    step = result.trace[2]
    assert step["actor"] == "agent" and step["reason"] == "createOrder 확인이 필요하다."
    assert "order.js" in step["result"]


def test_find_callers_tool_returns_static_facts(fixtures_dir: Path) -> None:
    model = FakeModel([actions(("find_callers", "createOrder")), response()])
    run(fixtures_dir, model)
    observed = json.loads(model.calls[1][1])["observations"][0]["result"]
    assert observed[0]["name"] == "handleOrderRequest" and observed[0]["facts"]


def test_unknown_function_is_reported_not_crashed(fixtures_dir: Path) -> None:
    model = FakeModel([actions(("read_function", "invented")), response()])
    result = run(fixtures_dir, model)
    assert result.summary and "찾지 못함" in result.trace[2]["result"]


def test_loop_stops_at_max_turns(fixtures_dir: Path) -> None:
    looping = actions(("read_function", "createOrder"))
    final = json.dumps({**json.loads(response()), **json.loads(looping)}, ensure_ascii=False)
    model = FakeModel([looping] * (MAX_TURNS - 1) + [final])
    result = run(fixtures_dir, model)
    assert len(model.calls) == MAX_TURNS and result.summary
    assert json.loads(model.calls[-1][1])["turns_left"] == 0
    agent_steps = [step for step in result.trace if step["actor"] == "agent" and step["tool"] != "answer"]
    assert len(agent_steps) == MAX_TURNS - 1
    assert all(step["result"] == "중복 요청이라 생략" for step in agent_steps[1:])


def test_actions_only_on_last_turn_falls_back(fixtures_dir: Path) -> None:
    model = FakeModel(actions(("read_function", "createOrder")))
    result = run(fixtures_dir, model)
    assert len(model.calls) == MAX_TURNS + 1 and result.summary is None and result.warnings
    assert all(node.facts for node in result.impacts)


def test_hallucinated_function_is_discarded(fixtures_dir: Path) -> None:
    model = FakeModel(response(impacts=[{"name": "invented", "file": "invented.js", "risk": "확인해야 합니다.", "risk_level": "high"}]))
    result = run(fixtures_dir, model)
    assert {node.name for node in result.impacts} == {"createOrder", "preparePayment", "handleOrderRequest"}
    assert all(node.risk is None for node in result.impacts)


def test_model_exception_is_sanitized(fixtures_dir: Path) -> None:
    key = secrets.token_urlsafe()

    class FailingModel:
        def complete(self, system: str, user: str) -> str:
            raise RuntimeError(key)

    result = run(fixtures_dir, FailingModel())
    assert result.summary is None and result.warnings
    assert key not in " ".join(result.warnings)


def test_missing_provider_degrades_to_static(fixtures_dir: Path, monkeypatch) -> None:
    def missing():
        from code_impact.models import ModelError
        raise ModelError()

    monkeypatch.setattr("code_impact.orchestrator.create_model", missing)
    result = analyze(fixtures_dir, "price.js", 2, 2)
    assert result.summary is None and len(result.impacts) == 3 and result.warnings


def test_root_boundary_before_resolver(fixtures_dir: Path, tmp_path: Path) -> None:
    with pytest.raises(SourceNotFound):
        analyze(tmp_path, fixtures_dir / "price.js", 2, 2, model=FakeModel(response()))


@pytest.mark.parametrize("invalid", [
    '{"summary": "x", "impacts": {}, "need_more": []}',
    '{"summary": "x", "impacts": [], "actions": "bad"}',
    '{"actions": [{"tool": "rm_rf", "args": {"name": "x"}}]}',
    '{"summary": "반드시 오류", "impacts": []}',
])
def test_invalid_schema_and_assertive_claims_fall_back(fixtures_dir: Path, invalid: str) -> None:
    result = run(fixtures_dir, FakeModel([invalid, invalid]))
    assert result.summary is None and result.warnings


def test_transient_model_error_uses_retry(fixtures_dir: Path) -> None:
    class FlakyModel(FakeModel):
        def complete(self, system: str, user: str) -> str:
            if not self.calls:
                self.calls.append((system, user))
                raise RuntimeError("HTTP 503")
            return super().complete(system, user)

    model = FlakyModel([response()])
    result = run(fixtures_dir, model)
    assert len(model.calls) == 2 and result.summary and not result.warnings

import json
import secrets
from pathlib import Path

import pytest

from code_impact.model import FakeModel
from code_impact.models import SourceNotFound
from code_impact.orchestrator import analyze


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


def test_need_more_is_exactly_one_followup(fixtures_dir: Path) -> None:
    model = FakeModel([response(need_more=["createOrder"]), response(need_more=["createOrder"])])
    result = run(fixtures_dir, model)
    assert result.summary and len(model.calls) == 2
    additional = json.loads(model.calls[1][1])["additional_context"]
    assert additional[0]["name"] == "createOrder" and "saveOrder(amount)" in additional[0]["source"]


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
    '{"summary": "x", "impacts": [], "need_more": "bad"}',
    '{"summary": "반드시 오류", "impacts": []}',
])
def test_invalid_schema_and_assertive_claims_fall_back(fixtures_dir: Path, invalid: str) -> None:
    result = run(fixtures_dir, FakeModel([invalid, invalid]))
    assert result.summary is None and result.warnings

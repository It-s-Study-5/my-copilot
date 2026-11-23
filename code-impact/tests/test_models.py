from dataclasses import is_dataclass

import pytest

from code_impact.models import AnalysisResult, CallSite, Function, ImpactNode


def test_dataclasses() -> None:
    target = Function("calculatePrice", "price.js", 2, 5)
    call = CallSite("calculatePrice", 4, 10)
    impact = ImpactNode("preparePayment", "payment.js", 3, 5, 1, calls=[call])
    result = AnalysisResult(target, impacts=[impact])
    assert all(is_dataclass(value) for value in (target, call, impact, result))
    assert result.target is target
    assert result.summary is None and impact.risk is None and impact.risk_level is None


@pytest.mark.parametrize(("depth", "relation"), [(1, "direct"), (2, "indirect"), (3, "indirect")])
def test_relation_is_derived(depth: int, relation: str) -> None:
    node = ImpactNode("caller", "caller.js", 1, 3, depth)
    assert node.relation == relation


def test_defaults_are_not_shared() -> None:
    first = ImpactNode("a", "a.js", 1, 1, 1)
    second = ImpactNode("b", "b.js", 1, 1, 1)
    first.facts.append("확인된 사실")
    assert second.facts == []

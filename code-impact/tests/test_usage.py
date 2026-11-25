from pathlib import Path

import pytest

from code_impact.context import read_context
from code_impact.hierarchy import find_callers
from code_impact.resolver import resolve
from code_impact.usage import inspect_usage


def test_expected_usage(fixtures_dir: Path) -> None:
    target = resolve(fixtures_dir / "price.js", 2, 2)
    nodes = find_callers(fixtures_dir, target, 3)
    read_context(nodes)
    order = next(node for node in nodes if node.name == "createOrder")
    assert set(inspect_usage(order, "calculatePrice")) >= {
        "calculatePrice()의 반환값을 amount에 저장한다.",
        "amount를 조건문(amount <= 0)에서 검사한다.",
        "amount를 saveOrder()에 전달한다.",
        "price, quantity를 인자로 전달한다.",
    }
    for name, callee in [("preparePayment", "calculatePrice"), ("handleOrderRequest", "createOrder")]:
        node = next(node for node in nodes if node.name == name)
        assert f"{callee}()의 결과를 그대로 반환한다." in inspect_usage(node, callee)


@pytest.mark.parametrize(("line", "expected"), [
    (1, "calculatePrice()의 반환값을 사용하지 않는다."),
    (5, "amount를 조건문(amount > 0)에서 검사한다."),
    (9, "amount.toFixed()를 호출한다."),
])
def test_usage_fixture(edge_dir: Path, line: int, expected: str) -> None:
    assert expected in inspect_usage(resolve(edge_dir / "usage.js", line, 3), "calculatePrice")


@pytest.mark.parametrize(("body", "expected"), [
    ("const amount = target(); save(amount);", "amount를 save()에 전달한다."),
    ("save(target());", "target()의 결과를 save()에 전달한다."),
    ("const amount = target(); while(amount > 0) { break; }", "amount를 조건문(amount > 0)에서 검사한다."),
    ("const amount = target(); amount && save();", "amount를 조건문(amount && save())에서 검사한다."),
    ("const amount = target(); return amount.value;", "amount.value에 접근한다."),
])
def test_fact_forms(tmp_path: Path, body: str, expected: str) -> None:
    path = tmp_path / "sample.js"
    path.write_text(f"function caller() {{ {body} }}", encoding="utf-8")
    assert expected in inspect_usage(resolve(path, 0, 20), "target")


def test_deduplication_and_no_nested_facts(tmp_path: Path) -> None:
    path = tmp_path / "sample.js"
    path.write_text("function caller() { target(); target(); function nested(){ return target(); } }", encoding="utf-8")
    facts = inspect_usage(resolve(path, 0, 25), "target")
    assert facts == ["target()의 반환값을 사용하지 않는다."]


def test_stop_at_reassignment_and_ignore_shadow(tmp_path: Path) -> None:
    path = tmp_path / "sample.js"
    path.write_text("function caller(){let amount=target(); {const amount=0; save(amount);} amount=0; save(amount);}", encoding="utf-8")
    facts = inspect_usage(resolve(path, 0, 25), "target")
    assert "amount를 save()에 전달한다." not in facts


def test_aliased_calls_use_resolved_callee(tmp_path: Path) -> None:
    path = tmp_path / "target.js"
    path.write_text("export function target() {return 1;}", encoding="utf-8")
    (tmp_path / "use.js").write_text('import {target as alias} from "./target.js"; function caller(){ return alias(); }', encoding="utf-8")
    node = find_callers(tmp_path, resolve(path, 0, 25), 3)[0]
    assert "target()의 결과를 그대로 반환한다." in inspect_usage(node, "target")


def test_passed_argument_is_not_directly_tested(tmp_path: Path) -> None:
    path = tmp_path / "logical.js"
    path.write_text("function caller(){const amount=target(); other && save(amount);}", encoding="utf-8")
    facts = inspect_usage(resolve(path, 0, 25), "target")
    assert "amount를 save()에 전달한다." in facts
    assert not any("조건문" in fact for fact in facts)


def test_direct_result_method_access(tmp_path: Path) -> None:
    path = tmp_path / "direct.js"
    path.write_text("function caller(){return target().toFixed();}", encoding="utf-8")
    assert "target().toFixed()를 호출한다." in inspect_usage(resolve(path, 0, 25), "target")


def test_call_inside_anonymous_callback(tmp_path: Path) -> None:
    path = tmp_path / "anon.js"
    path.write_text("function caller(items){ useEffect(() => { target(); }); return items.map(i => target(i)); }", encoding="utf-8")
    facts = inspect_usage(resolve(path, 0, 25), "target")
    assert "useEffect()에 넘긴 익명 함수 안에서 target()를 호출한다." in facts
    assert "items.map()에 넘긴 익명 함수 안에서 target()를 호출한다." in facts
    assert "target()의 결과를 익명 함수의 반환값으로 돌려준다." in facts


def test_chained_call_facts_belong_to_innermost_call(tmp_path: Path) -> None:
    path = tmp_path / "target.js"
    path.write_text("export function target() {return 1;}", encoding="utf-8")
    (tmp_path / "use.js").write_text('import {target} from "./target.js";\nfunction caller(){ target(1).then(save).catch(log); }', encoding="utf-8")
    facts = inspect_usage(find_callers(tmp_path, resolve(path, 0, 25), 3)[0], "target")
    assert facts == ["1를 인자로 전달한다."]


@pytest.mark.parametrize(("body", "expected"), [
    ("return target.call(null, 1, 2);", ["target()의 결과를 그대로 반환한다.", "1, 2를 인자로 전달한다."]),
    ("return target.apply(null, args);", ["target()의 결과를 그대로 반환한다.", "args를 인자 목록으로 전달한다."]),
    ('return ns["target"](1);', ["target()의 결과를 그대로 반환한다.", "1를 인자로 전달한다."]),
])
def test_call_apply_and_string_key_facts(tmp_path: Path, body: str, expected: list[str]) -> None:
    path = tmp_path / "sample.js"
    path.write_text(f"function caller(args) {{ {body} }}", encoding="utf-8")
    assert inspect_usage(resolve(path, 0, 25), "target") == expected


def test_callback_facts(tmp_path: Path) -> None:
    target = tmp_path / "price.js"
    target.write_text("export function price(p) { return p; }", encoding="utf-8")
    (tmp_path / "use.jsx").write_text(
        'import { price } from "./price.js";\n'
        "function viaMap(items) { return items.map(price); }\n"
        "function viaJsx() { return <button onClick={price}>x</button>; }\n"
        "function viaBind() { return price.bind(null, 1); }\n", encoding="utf-8",
    )
    facts = {node.name: inspect_usage(node, "price") for node in find_callers(tmp_path, resolve(target, 0, 30), 3)}
    assert facts == {
        "viaMap": ["price를 items.map()의 콜백으로 전달한다."],
        "viaJsx": ["price를 onClick 속성으로 전달한다."],
        "viaBind": ["price.bind()로 묶은 함수를 만든다."],
    }


def test_promise_chain_is_not_a_fact(tmp_path: Path) -> None:
    path = tmp_path / "promise.js"
    path.write_text("function caller(){ target().then(a).catch(b).finally(c); const p = target(); p.then(a); return target().toFixed(); }", encoding="utf-8")
    facts = inspect_usage(resolve(path, 0, 25), "target")
    assert not any(method in fact for fact in facts for method in (".then(", ".catch(", ".finally("))
    assert "target().toFixed()를 호출한다." in facts

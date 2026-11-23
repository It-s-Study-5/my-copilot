from pathlib import Path

import pytest

from code_impact.hierarchy import find_callers
from code_impact.models import SourceNotFound
from code_impact.resolver import resolve


def test_expected_hierarchy(fixtures_dir: Path) -> None:
    target = resolve(fixtures_dir / "price.js", 2, 2)
    result = find_callers(fixtures_dir, target, 3)
    assert {(node.name, node.depth, node.relation) for node in result} == {
        ("preparePayment", 1, "direct"), ("createOrder", 1, "direct"),
        ("handleOrderRequest", 2, "indirect"),
    }
    assert not result.truncated and not result.warnings
    handler = next(node for node in result if node.name == "handleOrderRequest")
    assert [(call.callee, call.line, call.col) for call in handler.calls] == [("createOrder", 4, 10)]


def test_depth_limit(fixtures_dir: Path) -> None:
    result = find_callers(fixtures_dir, resolve(fixtures_dir / "price.js", 2, 2), 1)
    assert {node.name for node in result} == {"preparePayment", "createOrder"}
    assert result.truncated


def test_cycle(edge_dir: Path) -> None:
    result = find_callers(edge_dir, resolve(edge_dir / "cycle.js", 1, 2), 20)
    assert [(node.name, node.depth) for node in result] == [("b", 1)]
    assert not result.truncated


def test_same_name_import(edge_dir: Path) -> None:
    a = find_callers(edge_dir, resolve(edge_dir / "same_a.js", 1, 2), 3)
    b = find_callers(edge_dir, resolve(edge_dir / "same_b.js", 1, 2), 3)
    assert [node.name for node in a] == ["useSame"]
    assert not b and not a.warnings


def test_excluded_and_module_and_limit(tmp_path: Path) -> None:
    target = tmp_path / "target.js"
    target.write_text("export function target() { return 1; }\n", encoding="utf-8")
    ignored = tmp_path / "node_modules"
    ignored.mkdir()
    (ignored / "ignored.js").write_text("function ignored() { target(); }", encoding="utf-8")
    (tmp_path / "module.js").write_text('import {target} from "./target.js"; target();', encoding="utf-8")
    result = find_callers(tmp_path, resolve(target, 0, 20), 3)
    assert [node.name for node in result] == ["<module>"]
    assert not result.truncated
    (tmp_path / "many.js").write_text("\n".join(f"function f{i}() {{ target(); }}" for i in range(55)), encoding="utf-8")
    result = find_callers(tmp_path, resolve(target, 0, 20), 3)
    assert len(result) == 50 and result.truncated


@pytest.mark.parametrize("binding,call", [
    ('import {same as alias} from "./a.js";', 'alias()'),
    ('import * as ns from "./a.js";', 'ns.same()'),
    ('const {same: alias} = require("./a.js");', 'alias()'),
    ('const ns = require("./a.js");', 'ns.same()'),
    ('const alias = require("./a.js").same;', 'alias()'),
])
def test_import_and_require_aliases(tmp_path: Path, binding: str, call: str) -> None:
    a = tmp_path / "a.js"
    b = tmp_path / "b.js"
    a.write_text("export function same() { return 1; }", encoding="utf-8")
    b.write_text("export function same() { return 2; }", encoding="utf-8")
    (tmp_path / "use.js").write_text(f"{binding}\nfunction use() {{ return {call}; }}", encoding="utf-8")
    assert [node.name for node in find_callers(tmp_path, resolve(a, 0, 25), 3)] == ["use"]
    assert not find_callers(tmp_path, resolve(b, 0, 25), 3)


def test_ambiguous_candidates(tmp_path: Path) -> None:
    for name in ("a", "b"):
        (tmp_path / f"{name}.js").write_text("function same() { return 1; }", encoding="utf-8")
    (tmp_path / "use.js").write_text("function use() { same(); }", encoding="utf-8")
    for name in ("a", "b"):
        result = find_callers(tmp_path, resolve(tmp_path / f"{name}.js", 0, 20), 3)
        assert [node.name for node in result] == ["use"]
        assert "동명 함수" in result.warnings[0]


def test_root_boundary(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    outside = tmp_path / "outside.js"
    outside.write_text("function outside() { return 1; }", encoding="utf-8")
    (root / "link.js").symlink_to(outside)
    with pytest.raises(SourceNotFound):
        find_callers(root, resolve(outside, 0, 25), 3)


def test_shortest_depth_and_multiple_calls(tmp_path: Path) -> None:
    path = tmp_path / "sample.js"
    path.write_text("function target() {}\nfunction middle() {target();}\nfunction top(){target(); target(); middle();}\n", encoding="utf-8")
    result = find_callers(tmp_path, resolve(path, 0, 10), 3)
    top = next(node for node in result if node.name == "top")
    assert top.depth == 1 and len(top.calls) == 2
    assert all(call.callee == "target" for call in top.calls)


def test_named_expression_variable_binding(tmp_path: Path) -> None:
    path = tmp_path / "named.js"
    path.write_text("const variable = function named() { return 1; };\nfunction use(){ return variable(); }", encoding="utf-8")
    result = find_callers(tmp_path, resolve(path, 0, 35), 3)
    assert [node.name for node in result] == ["use"]


def test_nonfunction_shadow_does_not_call_imported_target(tmp_path: Path) -> None:
    path = tmp_path / "target.js"
    path.write_text("export function target() {}", encoding="utf-8")
    (tmp_path / "use.js").write_text('import { target } from "./target.js"; function use(){ const target = other; target(); }', encoding="utf-8")
    assert not find_callers(tmp_path, resolve(path, 0, 20), 3)


def test_namespace_shadow_does_not_call_imported_target(tmp_path: Path) -> None:
    path = tmp_path / "target.js"
    path.write_text("export function target() {}", encoding="utf-8")
    (tmp_path / "use.js").write_text('import * as ns from "./target.js"; function use(ns){ return ns.target(); }', encoding="utf-8")
    assert not find_callers(tmp_path, resolve(path, 0, 20), 3)


def test_diamond_records_both_lower_level_calls(tmp_path: Path) -> None:
    path = tmp_path / "diamond.js"
    path.write_text("function target() {}\nfunction a(){target();}\nfunction b(){target();}\nfunction top(){a(); b();}", encoding="utf-8")
    result = find_callers(tmp_path, resolve(path, 0, 15), 3)
    top = next(node for node in result if node.name == "top")
    assert top.depth == 2 and {call.callee for call in top.calls} == {"a", "b"}


def test_static_default_import(tmp_path: Path) -> None:
    path = tmp_path / "default.js"
    path.write_text("export default function target(){return 1;}", encoding="utf-8")
    (tmp_path / "use.js").write_text('import alias from "./default.js"; function use(){ return alias(); }', encoding="utf-8")
    assert [node.name for node in find_callers(tmp_path, resolve(path, 0, 35), 3)] == ["use"]


def test_scoped_require_bindings(tmp_path: Path) -> None:
    for name in ("a", "b"):
        (tmp_path / f"{name}.js").write_text("exports.same = function same() {return 1;};", encoding="utf-8")
    (tmp_path / "use.js").write_text('function useA(){const {same}=require("./a.js"); return same();}\nfunction useB(){const {same}=require("./b.js"); return same();}', encoding="utf-8")
    for name, caller in [("a", "useA"), ("b", "useB")]:
        result = find_callers(tmp_path, resolve(tmp_path / f"{name}.js", 0, 35), 3)
        assert [node.name for node in result] == [caller]


def test_class_method_call(tmp_path: Path) -> None:
    path = tmp_path / "methods.js"
    path.write_text("class C { compute() {return 1;} }\nfunction use(){ const obj=new C(); return obj.compute(); }", encoding="utf-8")
    assert [node.name for node in find_callers(tmp_path, resolve(path, 0, 20), 3)] == ["use"]


def test_named_expression_import_uses_exported_variable(tmp_path: Path) -> None:
    path = tmp_path / "named.js"
    path.write_text("export const variable = function named(){ return 1; };", encoding="utf-8")
    (tmp_path / "use.js").write_text('import {variable} from "./named.js"; function use(){return variable();}', encoding="utf-8")
    assert [node.name for node in find_callers(tmp_path, resolve(path, 0, 45), 3)] == ["use"]


def test_parameter_default_value_does_not_shadow_target(tmp_path: Path) -> None:
    path = tmp_path / "defaults.js"
    path.write_text("function target(){return 1;}\nfunction use(value=target()){return value;}", encoding="utf-8")
    assert [node.name for node in find_callers(tmp_path, resolve(path, 0, 15), 3)] == ["use"]

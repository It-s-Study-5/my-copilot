from pathlib import Path

import pytest

from code_impact.models import NotInFunction, SourceNotFound, UnsupportedLanguage
from code_impact.resolver import enclosing_function, parse_file, resolve


@pytest.mark.parametrize("line", [1, 2, 4])
def test_price_declaration_body_and_closing(fixtures_dir: Path, line: int) -> None:
    function = resolve(fixtures_dir / "price.js", line, 0)
    assert (function.name, function.start_line, function.end_line) == ("calculatePrice", 2, 5)


def test_nested(edge_dir: Path) -> None:
    path = edge_dir / "nested.js"
    assert resolve(path, 2, 4).name == "inner"
    assert resolve(path, 4, 4).name == "outer"
    assert enclosing_function(parse_file(path), 2, 4).type == "function_declaration"


@pytest.mark.parametrize("line", [1, 3])
def test_nested_boundary_indentation(edge_dir: Path, line: int) -> None:
    assert resolve(edge_dir / "nested.js", line, 0).name == "inner"


def test_arrow_and_methods(edge_dir: Path) -> None:
    assert resolve(edge_dir / "arrow.js", 1, 3).name == "double"
    assert resolve(edge_dir / "methods.js", 2, 4).name == "compute"
    assert resolve(edge_dir / "methods.js", 7, 4).name == "computeValue"


@pytest.mark.parametrize("suffix", [".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"])
def test_supported_extensions(tmp_path: Path, suffix: str) -> None:
    path = tmp_path / f"sample{suffix}"
    path.write_text("const fn = function(x) { return x; };\n", encoding="utf-8")
    assert resolve(path, 0, 20).name == "fn"


def test_anonymous_and_property_name(tmp_path: Path) -> None:
    path = tmp_path / "sample.js"
    path.write_text("use(function() { return 1; });\nconst obj = { prop: () => 2 };\n", encoding="utf-8")
    assert resolve(path, 0, 20).name == "<anonymous>@1"
    assert resolve(path, 1, 25).name == "prop"


def test_errors(fixtures_dir: Path, tmp_path: Path) -> None:
    with pytest.raises(NotInFunction):
        resolve(fixtures_dir / "price.js", 0, 0)
    with pytest.raises(NotInFunction):
        resolve(fixtures_dir / "price.js", -1, 0)
    path = tmp_path / "unsupported.txt"
    path.write_text("hello", encoding="utf-8")
    with pytest.raises(UnsupportedLanguage):
        resolve(path, 0, 0)
    with pytest.raises(SourceNotFound):
        resolve(tmp_path / "missing.js", 0, 0)


def test_utf16_column_selects_correct_function(tmp_path: Path) -> None:
    path = tmp_path / "unicode.js"
    source = 'const emoji = "😀"; const f = () => 1; const g = () => 2;'
    path.write_text(source, encoding="utf-8")
    col = len(source[:source.index("=> 2")].encode("utf-16-le")) // 2
    assert resolve(path, 0, col).name == "g"


@pytest.mark.parametrize(("suffix", "source", "name"), [
    (".ts", "interface Input {value: number;}\nexport function typed(input: Input): number {return input.value;}", "typed"),
    (".tsx", "export const View = (props: {label: string}) => <span>{props.label}</span>;", "View"),
    (".jsx", "export const View = () => <span>Hello</span>;", "View"),
])
def test_typescript_and_jsx_syntax(tmp_path: Path, suffix: str, source: str, name: str) -> None:
    path = tmp_path / f"typed{suffix}"
    path.write_text(source, encoding="utf-8")
    line = 1 if suffix == ".ts" else 0
    assert resolve(path, line, 30).name == name


def test_property_assignment_name(tmp_path: Path) -> None:
    path = tmp_path / "assigned.js"
    path.write_text("obj.run = () => {return 1;};", encoding="utf-8")
    assert resolve(path, 0, 20).name == "run"

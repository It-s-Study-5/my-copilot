from pathlib import Path

from code_impact.context import read_context
from code_impact.hierarchy import find_callers
from code_impact.models import CallSite, ImpactNode
from code_impact.resolver import resolve


def test_exact_source(fixtures_dir: Path) -> None:
    target = resolve(fixtures_dir / "price.js", 2, 2)
    nodes = find_callers(fixtures_dir, target, 3)
    read_context([target, *nodes])
    order = next(node for node in nodes if node.name == "createOrder")
    content = (fixtures_dir / "order.js").read_bytes()
    expected = content[content.index(b"function createOrder"):].decode("utf-8").rstrip("\n")
    assert order.source == expected
    assert target.source.startswith("function calculatePrice")
    assert (order.start_line, order.end_line) == (3, 9)


def test_long_function_and_target(tmp_path: Path) -> None:
    path = tmp_path / "long.js"
    lines = ["function long() {", *[f"  const x{i} = {i};" for i in range(240)], "  target();", "}"]
    path.write_text("\n".join(lines), encoding="utf-8")
    target = resolve(path, 100, 5)
    node = ImpactNode(target.name, target.file, 1, len(lines), 1, calls=[CallSite("target", 242, 3)], path=path, node=target.node)
    read_context([node, target])
    assert node.source_truncated and target.source_truncated
    assert "target();" in node.source and "x239 = 239" in node.source
    assert "x100 = 100" not in node.source and "일부 문맥" in node.source
    assert node.end_line == len(lines)


def test_reads_each_file_once(tmp_path: Path, monkeypatch) -> None:
    path = tmp_path / "two.js"
    path.write_text("function a(){return 1;}\nfunction b(){return 2;}\n", encoding="utf-8")
    nodes = [resolve(path, 0, 15), resolve(path, 1, 15)]
    original = Path.read_bytes
    reads: list[Path] = []

    def counted(self: Path) -> bytes:
        reads.append(self)
        return original(self)

    monkeypatch.setattr(Path, "read_bytes", counted)
    read_context(nodes)
    assert reads == [path]
    assert nodes[0].source == "function a(){return 1;}"
    assert nodes[1].source == "function b(){return 2;}"

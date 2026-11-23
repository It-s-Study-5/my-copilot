from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path

from tree_sitter import Node, Tree
from tree_sitter_language_pack import get_parser

from .models import Function, NotInFunction, SourceNotFound, UnsupportedLanguage

LANGUAGES = {
    ".js": "javascript", ".jsx": "javascript", ".mjs": "javascript",
    ".cjs": "javascript", ".ts": "typescript", ".tsx": "tsx",
}
FUNCTION_TYPES = {
    "function_declaration", "function_expression", "arrow_function",
    "generator_function_declaration", "generator_function", "method_definition",
}


def walk(node: Node, *, skip_functions: bool = False) -> Iterator[Node]:
    stack = [node]
    while stack:
        current = stack.pop()
        yield current
        if skip_functions and current != node and current.type in FUNCTION_TYPES:
            continue
        stack.extend(reversed(current.named_children))


def text(node: Node | None) -> str:
    return node.text.decode("utf-8") if node is not None else ""


def parse_file(file: str | Path) -> Tree:
    path = Path(file)
    if not path.is_file():
        raise SourceNotFound()
    language = LANGUAGES.get(path.suffix.lower())
    if language is None:
        raise UnsupportedLanguage()
    try:
        content = path.read_bytes()
        content.decode("utf-8")
    except (OSError, UnicodeError):
        raise SourceNotFound() from None
    return get_parser(language).parse(content)


def function_name(node: Node) -> str:
    name = node.child_by_field_name("name")
    if name is not None:
        return text(name).strip("\"'")
    parent = node.parent
    while parent is not None and parent.type in {"parenthesized_expression", "as_expression"}:
        parent = parent.parent
    if parent is not None:
        if parent.type in {"variable_declarator", "assignment_expression"}:
            name = parent.child_by_field_name("name") or parent.child_by_field_name("left")
            if name is not None and name.type == "member_expression":
                name = name.child_by_field_name("property")
        elif parent.type in {"pair", "public_field_definition", "field_definition"}:
            name = parent.child_by_field_name("key") or parent.child_by_field_name("property")
        if name is not None:
            return text(name).strip("\"'")
    return f"<anonymous>@{node.start_point.row + 1}"


def enclosing_function(tree: Tree | Node, line: int, byte_col: int) -> Node | None:
    root = tree.root_node if isinstance(tree, Tree) else tree
    point = (line, byte_col)
    if not tuple(root.start_point) <= point < tuple(root.end_point):
        return None
    node = root.descendant_for_point_range(point, point)
    while node is not None:
        if node.type in FUNCTION_TYPES:
            return node
        if node == root:
            break
        node = node.parent
    return None


def function_from_node(node: Node, path: Path, root: Path | None = None) -> Function:
    return Function(
        function_name(node), path.relative_to(root).as_posix() if root else str(path),
        node.start_point.row + 1, node.end_point.row + 1, path=path, node=node,
    )


def safe_path(root: Path, file: str | Path) -> Path:
    try:
        supplied = Path(file)
        path = (supplied if supplied.is_absolute() else root / supplied).resolve()
        if not root.is_dir() or not path.is_file() or not path.is_relative_to(root):
            raise SourceNotFound()
        return path
    except OSError:
        raise SourceNotFound() from None


def resolve(file: str | Path, line: int, col: int) -> Function:
    path = Path(file).resolve()
    tree = parse_file(path)
    lines = text(tree.root_node).splitlines()
    if line < 0 or col < 0 or line >= len(lines):
        raise NotInFunction()
    # VS Code 열은 UTF-16 단위, tree-sitter 열은 UTF-8 바이트 단위이다.
    prefix = lines[line].encode("utf-16-le")[:col * 2].decode("utf-16-le", errors="ignore")
    node = enclosing_function(tree, line, len(prefix.encode("utf-8")))
    candidates = [
        item for item in walk(tree.root_node) if item.type in FUNCTION_TYPES
        and item.start_point.row <= line <= item.end_point.row
    ]
    for candidate in sorted(candidates, key=lambda item: item.end_byte - item.start_byte):
        leading = lines[line].encode("utf-8")[:candidate.start_point.column].decode("utf-8")
        declaration_prefix = not leading.strip() or re.fullmatch(
            r"\s*(?:export\s+)?(?:const|let|var)\s+[\w$]+\s*=\s*", leading,
        )
        # 중첩 선언 줄의 들여쓰기에도 가장 안쪽 함수를 선택한다.
        if node is None or (candidate.start_point.row == line and declaration_prefix and candidate.start_byte >= node.start_byte and candidate.end_byte <= node.end_byte):
            node = candidate
            break
    if node is None:
        raise NotInFunction()
    return function_from_node(node, path)

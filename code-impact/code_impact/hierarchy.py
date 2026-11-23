from __future__ import annotations

import os
from collections import deque
from dataclasses import dataclass
from pathlib import Path

from tree_sitter import Node, Tree

from .models import CallSite, Function, ImpactNode, SourceNotFound
from .resolver import (
    FUNCTION_TYPES, LANGUAGES, enclosing_function, function_from_node,
    parse_file, safe_path, text, walk,
)

EXCLUDED = {"node_modules", "dist", "out", "build", ".git", ".venv"}
MAX_NODES = 50


class CallerList(list[ImpactNode]):
    """Keep the documented list contract and carry traversal metadata internally."""

    def __init__(self) -> None:
        super().__init__()
        self.truncated = False
        self.warnings: list[str] = []


def identity(function: Function) -> tuple[str, int, int]:
    return (
        str(function.path or function.file),
        function.node.start_byte if function.node is not None else function.start_line,
        function.node.end_byte if function.node is not None else function.end_line,
    )


def _scope(node: Node) -> Node:
    parent = node.parent
    while parent is not None:
        if parent.type in {"program", "statement_block", "class_body"}:
            return parent
        parent = parent.parent
    return node


def _contains(container: Node, node: Node) -> bool:
    return container.start_byte <= node.start_byte and node.end_byte <= container.end_byte


def _binding_names(pattern: Node | None) -> set[str]:
    if pattern is None:
        return set()
    if pattern.type in {"identifier", "shorthand_property_identifier_pattern"}:
        return {text(pattern)}
    if pattern.type == "assignment_pattern":
        return _binding_names(pattern.child_by_field_name("left"))
    if pattern.type == "pair_pattern":
        return _binding_names(pattern.child_by_field_name("value"))
    if pattern.type in {"required_parameter", "optional_parameter"}:
        return _binding_names(pattern.child_by_field_name("pattern"))
    return set().union(*(_binding_names(child) for child in pattern.named_children))


def _callable_names(function: Function, call: Node) -> set[str]:
    node = function.node
    parent = node.parent
    if parent is not None and parent.type == "variable_declarator":
        names = _binding_names(parent.child_by_field_name("name"))
        if _contains(node, call):
            names.add(function.name)
        return names
    return {function.name}


@dataclass
class ImportBinding:
    scope: Node
    module: Path | None
    exported: str


@dataclass
class Edge:
    caller: Function
    callee: Function
    call: CallSite
    ambiguous: bool = False


class Project:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).resolve()
        if not self.root.is_dir():
            raise SourceNotFound()
        self.trees: dict[Path, Tree] = {}
        self.functions: list[Function] = []
        self.bindings: dict[Path, dict[str, list[ImportBinding]]] = {}
        try:
            for directory, dirs, files in os.walk(self.root, onerror=self._walk_error):
                dirs[:] = sorted(
                    name for name in dirs if name not in EXCLUDED
                    and not (Path(directory) / name).is_symlink()
                )
                for name in sorted(files):
                    candidate = Path(directory) / name
                    if candidate.suffix.lower() not in LANGUAGES:
                        continue
                    # 심볼릭 링크는 root 밖뿐 아니라 중복/순환 인덱싱도 피한다.
                    if candidate.is_symlink():
                        continue
                    path = safe_path(self.root, candidate)
                    tree = parse_file(path)
                    self.trees[path] = tree
                    self.functions.extend(
                        function_from_node(node, path, self.root)
                        for node in walk(tree.root_node) if node.type in FUNCTION_TYPES
                    )
        except OSError:
            raise SourceNotFound() from None
        for path, tree in self.trees.items():
            self.bindings[path] = self._imports(path, tree)
        self.functions_by_path: dict[Path, list[Function]] = {path: [] for path in self.trees}
        self.functions_by_name: dict[str, list[Function]] = {}
        self.local_functions: dict[Path, dict[str, list[Function]]] = {path: {} for path in self.trees}
        self.declarations: dict[Path, dict[str, list[Node]]] = {path: {} for path in self.trees}
        for function in self.functions:
            self.functions_by_path[function.path].append(function)
            self.functions_by_name.setdefault(function.name, []).append(function)
            names = _callable_names(function, self.trees[function.path].root_node) | {function.name}
            for name in names:
                self.local_functions[function.path].setdefault(name, []).append(function)
        for path, tree in self.trees.items():
            for declaration in walk(tree.root_node):
                if declaration.type == "variable_declarator":
                    for name in _binding_names(declaration.child_by_field_name("name")):
                        self.declarations[path].setdefault(name, []).append(declaration)

    @staticmethod
    def _walk_error(error: OSError) -> None:
        raise SourceNotFound() from None

    def _module_path(self, path: Path, specifier: str) -> Path | None:
        if not specifier.startswith("."):
            return None
        base = (path.parent / specifier).resolve()
        candidates = [base]
        if not base.suffix:
            candidates.extend(Path(str(base) + suffix) for suffix in LANGUAGES)
            candidates.extend(base / ("index" + suffix) for suffix in LANGUAGES)
        elif base.suffix == ".js":
            candidates.extend(base.with_suffix(suffix) for suffix in (".ts", ".tsx"))
        return next((item for item in candidates if item in self.trees), None)

    def _imports(self, path: Path, tree: Tree) -> dict[str, list[ImportBinding]]:
        bindings: dict[str, list[ImportBinding]] = {}

        def add(name: str, module: Path | None, exported: str, scope: Node) -> None:
            bindings.setdefault(name, []).append(ImportBinding(scope, module, exported))

        for node in walk(tree.root_node):
            if node.type == "import_statement":
                source = node.child_by_field_name("source")
                module = self._module_path(path, text(source).strip("\"'"))
                clause = next((child for child in node.named_children if child.type == "import_clause"), None)
                if clause is None:
                    continue
                for child in clause.named_children:
                    if child.type == "identifier":
                        add(text(child), module, "default", tree.root_node)
                    elif child.type == "namespace_import":
                        add(text(child.named_children[0]), module, "*", tree.root_node)
                    elif child.type == "named_imports":
                        for spec in child.named_children:
                            name = spec.child_by_field_name("name")
                            alias = spec.child_by_field_name("alias") or name
                            add(text(alias), module, text(name), tree.root_node)
            elif node.type == "variable_declarator":
                value = node.child_by_field_name("value")
                name = node.child_by_field_name("name")
                prop = None
                if value is not None and value.type == "member_expression":
                    prop = value.child_by_field_name("property")
                    value = value.child_by_field_name("object")
                if value is None or value.type != "call_expression" or text(value.child_by_field_name("function")) != "require":
                    continue
                args = value.child_by_field_name("arguments")
                if args is None or not args.named_children or args.named_children[0].type != "string":
                    continue
                module = self._module_path(path, text(args.named_children[0]).strip("\"'"))
                if name.type == "identifier":
                    add(text(name), module, text(prop) if prop is not None else "*", _scope(node))
                elif name.type == "object_pattern":
                    for part in name.named_children:
                        if part.type == "pair_pattern":
                            add(text(part.child_by_field_name("value")), module, text(part.child_by_field_name("key")), _scope(node))
                        elif part.type == "shorthand_property_identifier_pattern":
                            add(text(part), module, text(part), _scope(node))
        return bindings

    def _shadowed(self, path: Path, name: str, call: Node) -> bool:
        parent = call.parent
        while parent is not None:
            if parent.type in FUNCTION_TYPES:
                parameters = parent.child_by_field_name("parameters") or parent.child_by_field_name("parameter")
                if name in _binding_names(parameters):
                    return True
            parent = parent.parent
        declarations = [
            node for node in self.declarations[path].get(name, [])
            if _contains(_scope(node), call)
        ]
        if not declarations:
            return False
        declaration = min(declarations, key=lambda node: _scope(node).end_byte - _scope(node).start_byte)
        value = declaration.child_by_field_name("value")
        if value is not None and value.type in FUNCTION_TYPES:
            return False
        if value is not None and value.type == "member_expression":
            value = value.child_by_field_name("object")
        is_require = value is not None and value.type == "call_expression" and text(value.child_by_field_name("function")) == "require"
        return not is_require

    def _exported(self, path: Path | None, name: str) -> list[Function]:
        if path is None:
            return []
        functions = self.functions_by_path[path]
        root = self.trees[path].root_node
        if name != "default":
            for statement in self.trees[path].root_node.named_children:
                if statement.type != "export_statement":
                    continue
                for spec in walk(statement):
                    if spec.type == "export_specifier" and text(spec.child_by_field_name("alias")) == name:
                        name = text(spec.child_by_field_name("name"))
            return [function for function in functions if name in _callable_names(function, root)]
        for statement in self.trees[path].root_node.named_children:
            if statement.type == "export_statement" and any(child.type == "default" for child in statement.children):
                contained = [function for function in functions if _contains(statement, function.node)]
                if contained:
                    return contained[:1]
                value = statement.child_by_field_name("value")
                return [function for function in functions if text(value) in _callable_names(function, root)]
        # 단일 함수 CommonJS 모듈은 기본 export 후보로 취급한다.
        return [function for function in functions if len(functions) == 1]

    def _callees(self, path: Path, call: Node) -> list[Function]:
        expression = call.child_by_field_name("function")
        if expression is None:
            return []
        bindings: dict[str, tuple[Path | None, str]] = {}
        for name, candidates in self.bindings[path].items():
            visible = [binding for binding in candidates if _contains(binding.scope, call)]
            if visible:
                binding = min(visible, key=lambda item: item.scope.end_byte - item.scope.start_byte)
                bindings[name] = (binding.module, binding.exported)
        if expression.type == "identifier":
            name = text(expression)
            if self._shadowed(path, name, call):
                return []
            local = [
                function for function in self.local_functions[path].get(name, [])
                if name in _callable_names(function, call) and _contains(_scope(function.node), call)
            ]
            if local:
                closest = min(_scope(function.node).end_byte - _scope(function.node).start_byte for function in local)
                return [function for function in local if _scope(function.node).end_byte - _scope(function.node).start_byte == closest]
            if name in bindings:
                module, exported = bindings[name]
                return self._exported(module, "default" if exported == "*" else exported)
        elif expression.type == "member_expression":
            obj = text(expression.child_by_field_name("object"))
            name = text(expression.child_by_field_name("property"))
            if obj in bindings and self._shadowed(path, obj, call):
                return []
            if obj in bindings:
                module, exported = bindings[obj]
                if exported == "*":
                    return self._exported(module, name)
        else:
            # obj[name](), 콜백 전달, 동적 별칭 전파는 추적하지 않는다.
            return []
        return self.functions_by_name.get(name, [])

    def edges(self) -> list[Edge]:
        edges: list[Edge] = []
        for path, tree in self.trees.items():
            by_node = {function.node.id: function for function in self.functions_by_path[path]}
            module = Function("<module>", path.relative_to(self.root).as_posix(), 1, max(1, len(text(tree.root_node).splitlines())), path=path, node=tree.root_node)
            for call in walk(tree.root_node):
                if call.type != "call_expression":
                    continue
                candidates = self._callees(path, call)
                owner_node = enclosing_function(tree, call.start_point.row, call.start_point.column)
                caller = by_node[owner_node.id] if owner_node is not None else module
                for callee in candidates:
                    edges.append(Edge(caller, callee, CallSite(callee.name, call.start_point.row + 1, call.start_point.column + 1), len(candidates) > 1))
        return edges


def find_callers(root: str | Path, target: Function, depth: int) -> list[ImpactNode]:
    if type(depth) is not int or depth < 1:
        raise ValueError("depth는 1 이상의 정수여야 합니다.")
    project = Project(root)
    target_path = safe_path(project.root, target.path or target.file)
    matches = [function for function in project.functions if function.path == target_path and function.start_line == target.start_line and function.name == target.name]
    selected = next((function for function in matches if target.node is None or function.node.start_byte == target.node.start_byte), None)
    if selected is None:
        raise SourceNotFound("분석 대상 함수를 프로젝트에서 찾을 수 없습니다.")
    incoming: dict[tuple[str, int, int], list[Edge]] = {}
    for edge in project.edges():
        incoming.setdefault(identity(edge.callee), []).append(edge)
    result = CallerList()
    visited = {identity(selected): 0}
    nodes: dict[tuple[str, int, int], ImpactNode] = {}
    queue = deque([selected])
    while queue:
        callee = queue.popleft()
        current_depth = visited[identity(callee)]
        for edge in incoming.get(identity(callee), []):
            key = identity(edge.caller)
            next_depth = current_depth + 1
            if key in visited and visited[key] != next_depth:
                continue
            if next_depth > depth or (key not in visited and len(nodes) >= MAX_NODES):
                result.truncated = True
                continue
            if key not in visited:
                function = edge.caller
                node = ImpactNode(function.name, function.file, function.start_line, function.end_line, next_depth, path=function.path, node=function.node)
                nodes[key] = node
                visited[key] = next_depth
                result.append(node)
                queue.append(function)
            if edge.call not in nodes[key].calls:
                nodes[key].calls.append(edge.call)
            if edge.ambiguous:
                warning = f"동명 함수 {edge.callee.name}의 호출 대상을 좁히지 못해 후보를 포함했습니다."
                if warning not in result.warnings:
                    result.warnings.append(warning)
    return result

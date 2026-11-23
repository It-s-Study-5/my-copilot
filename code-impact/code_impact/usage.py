from __future__ import annotations

from tree_sitter import Node
from tree_sitter_language_pack import get_parser

from .models import Function, ImpactNode
from .resolver import FUNCTION_TYPES, LANGUAGES, text, walk


def _unwrap(node: Node) -> Node:
    while node.type in {"parenthesized_expression", "await_expression", "as_expression", "non_null_expression"} and node.named_children:
        node = node.named_children[0]
    return node


def _lift(node: Node) -> Node:
    while node.parent is not None and node.parent.type in {
        "parenthesized_expression", "await_expression", "as_expression", "non_null_expression",
    }:
        node = node.parent
    return node


def _condition(reference: Node, root: Node) -> str | None:
    parent = reference.parent
    while parent is not None and parent != root:
        if parent.type == "arguments":
            return None
        condition = parent.child_by_field_name("condition")
        if condition is not None and condition.start_byte <= reference.start_byte < condition.end_byte:
            return text(_unwrap(condition))
        if parent.type == "binary_expression" and text(parent.child_by_field_name("operator")) in {"&&", "||", "??"}:
            return text(parent)
        parent = parent.parent
    return None


def _use_facts(reference: Node, label: str, root: Node) -> list[str]:
    facts: list[str] = []
    condition = _condition(reference, root)
    if condition:
        facts.append(f"{label}를 조건문({condition})에서 검사한다.")
    lifted = _lift(reference)
    parent = lifted.parent
    if parent is not None and parent.type == "arguments":
        call = parent.parent
        if call is not None and call.type == "call_expression":
            facts.append(f"{label}를 {text(call.child_by_field_name('function'))}()에 전달한다.")
    if parent is not None and parent.type == "member_expression" and parent.child_by_field_name("object") == lifted:
        property_name = text(parent.child_by_field_name("property"))
        property_label = label.removesuffix("의 결과") if reference.type == "call_expression" else label
        if parent.parent is not None and parent.parent.type == "call_expression" and parent.parent.child_by_field_name("function") == parent:
            facts.append(f"{property_label}.{property_name}()를 호출한다.")
        else:
            facts.append(f"{property_label}.{property_name}에 접근한다.")
    return facts


def _scope(node: Node) -> Node:
    parent = node.parent
    while parent is not None and parent.type not in {"statement_block", "program"}:
        parent = parent.parent
    return parent or node


def _references(root: Node, declaration: Node, name: str) -> list[Node]:
    scope = _scope(declaration)
    nodes = list(walk(root, skip_functions=True))
    shadows = [
        node for node in nodes if node.type == "variable_declarator" and node != declaration
        and text(node.child_by_field_name("name")) == name
    ]
    stop = root.end_byte
    for node in nodes:
        if node.start_byte <= declaration.end_byte:
            continue
        if node.type in {"assignment_expression", "augmented_assignment_expression", "update_expression"}:
            left = node.child_by_field_name("left") or node.child_by_field_name("argument")
            if text(left) == name:
                stop = min(stop, node.start_byte)
    references: list[Node] = []
    for node in nodes:
        if node.type != "identifier" or text(node) != name or not declaration.end_byte <= node.start_byte < stop:
            continue
        if not scope.start_byte <= node.start_byte < scope.end_byte:
            continue
        if any(_scope(shadow).start_byte <= node.start_byte < _scope(shadow).end_byte for shadow in shadows):
            continue
        references.append(node)
    # 같은 함수의 같은 바인딩만 한 단계 추적한다. 재할당·별칭·중첩 함수는 추적하지 않는다.
    return references


def inspect_usage(caller: Function, callee_name: str) -> list[str]:
    root = caller.node
    if root is None:
        language = LANGUAGES.get(caller.path.suffix if caller.path else ".js", "javascript")
        tree = get_parser(language).parse(caller.source.encode("utf-8"))
        root = next((node for node in walk(tree.root_node) if node.type in FUNCTION_TYPES), tree.root_node)
    positions = {
        (call.line, call.col) for call in caller.calls if call.callee == callee_name
    } if isinstance(caller, ImpactNode) else set()
    facts: list[str] = []
    for call in walk(root, skip_functions=True):
        if call.type != "call_expression":
            continue
        expression = call.child_by_field_name("function")
        name = text(expression.child_by_field_name("property")) if expression.type == "member_expression" else text(expression)
        if positions:
            if (call.start_point.row + 1, call.start_point.column + 1) not in positions:
                continue
        elif name != callee_name:
            continue
        lifted = _lift(call)
        parent = lifted.parent
        if parent is not None and parent.type == "variable_declarator" and parent.child_by_field_name("value") == lifted:
            variable = parent.child_by_field_name("name")
            label = text(variable)
            facts.append(f"{callee_name}()의 반환값을 {label}에 저장한다.")
            if variable.type == "identifier":
                for reference in _references(root, parent, label):
                    facts.extend(_use_facts(reference, label, root))
        elif parent is not None and parent.type == "return_statement":
            facts.append(f"{callee_name}()의 결과를 그대로 반환한다.")
        elif parent is not None and parent.type == "expression_statement":
            facts.append(f"{callee_name}()의 반환값을 사용하지 않는다.")
        facts.extend(_use_facts(call, f"{callee_name}()의 결과", root))
        arguments = call.child_by_field_name("arguments")
        args = [text(argument) for argument in arguments.named_children if argument.type != "comment"]
        if args:
            facts.append(f"{', '.join(args)}를 인자로 전달한다.")
    return list(dict.fromkeys(facts))

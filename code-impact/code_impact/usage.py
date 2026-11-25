from __future__ import annotations

from tree_sitter import Node
from tree_sitter_language_pack import get_parser

from .hierarchy import callback_parent, is_bind
from .models import Function, ImpactNode
from .resolver import FUNCTION_TYPES, LANGUAGES, named_function, text, walk


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
            # Promise 체인(then/catch/finally)은 비동기 결과라면 당연한 사용이라 facts로 쓰지 않는다.
            if property_name not in {"then", "catch", "finally"}:
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


def _callback_facts(node: Node, callee_name: str) -> list[str]:
    # 콜백은 넘겨받는 쪽이 인자·반환값을 정하므로 넘긴 사실만 기록한다.
    if node.type == "call_expression" and is_bind(node):
        return [f"{callee_name}.bind()로 묶은 함수를 만든다."]
    if node.type not in {"identifier", "member_expression"}:
        return []
    receiver = callback_parent(node)
    if receiver is None:
        return []
    if receiver.type == "jsx_attribute":
        return [f"{callee_name}를 {text(receiver.named_children[0])} 속성으로 전달한다."]
    return [f"{callee_name}를 {text(receiver.child_by_field_name('function'))}()의 콜백으로 전달한다."]


def _key(expression: Node) -> str:
    key = expression.child_by_field_name("property") or expression.child_by_field_name("index")
    return text(key).strip("\"'") if key is not None and key.type != "template_string" else ""


def _owner(node: Node, root: Node) -> Node:
    parent = node.parent
    while parent is not None and parent != root and parent.type not in FUNCTION_TYPES:
        parent = parent.parent
    return parent or root


def _anonymous_fact(function: Node, callee_name: str) -> str:
    parent = _lift(function).parent
    if parent is not None and parent.type == "arguments" and parent.parent is not None and parent.parent.type == "call_expression":
        return f"{text(parent.parent.child_by_field_name('function'))}()에 넘긴 익명 함수 안에서 {callee_name}()를 호출한다."
    return f"익명 함수 안에서 {callee_name}()를 호출한다."


def inspect_usage(caller: Function, callee_name: str) -> list[str]:
    root = caller.node
    if root is None:
        language = LANGUAGES.get(caller.path.suffix if caller.path else ".js", "javascript")
        tree = get_parser(language).parse(caller.source.encode("utf-8"))
        root = next((node for node in walk(tree.root_node) if node.type in FUNCTION_TYPES), tree.root_node)
    sites = [call for call in caller.calls if call.callee == callee_name] if isinstance(caller, ImpactNode) else []
    positions = {(call.line, call.col) for call in sites if call.kind == "call"}
    callbacks = {(call.line, call.col) for call in sites if call.kind == "callback"}
    facts: list[str] = [
        fact for node in walk(root)
        if (node.start_point.row + 1, node.start_point.column + 1) in callbacks
        for fact in _callback_facts(node, callee_name)
    ]
    if callbacks and not positions:
        return list(dict.fromkeys(facts))
    for call in walk(root):
        if call.type != "call_expression":
            continue
        local = _owner(call, root)
        # 이름 있는 중첩 함수는 별도 호출자이고, 익명 함수 안의 호출만 이 함수 몫이다.
        # 최상위 익명 함수 안의 호출은 <module>(program 노드) 몫이다.
        owner = named_function(local) if local != root else root
        if owner != root and not (owner is None and root.type == "program"):
            continue
        expression = call.child_by_field_name("function")
        # 체인 호출(a().then())은 시작 위치가 같으므로 가장 안쪽 호출만 대상으로 본다.
        chained = expression.type == "member_expression" and _unwrap(expression.child_by_field_name("object")).type == "call_expression"
        method = _key(expression) if expression.type == "member_expression" and _key(expression) in {"call", "apply"} else None
        if method:
            expression = expression.child_by_field_name("object")
        name = _key(expression) if expression.type in {"member_expression", "subscript_expression"} else text(expression)
        if positions:
            if chained or (call.start_point.row + 1, call.start_point.column + 1) not in positions:
                continue
        elif name != callee_name:
            continue
        if local != root:
            facts.append(_anonymous_fact(local, callee_name))
        lifted = _lift(call)
        parent = lifted.parent
        if parent is not None and parent.type == "variable_declarator" and parent.child_by_field_name("value") == lifted:
            variable = parent.child_by_field_name("name")
            label = text(variable)
            facts.append(f"{callee_name}()의 반환값을 {label}에 저장한다.")
            if variable.type == "identifier":
                for reference in _references(local, parent, label):
                    facts.extend(_use_facts(reference, label, local))
        elif parent is not None and (parent.type == "return_statement" or (parent.type == "arrow_function" and parent.child_by_field_name("body") == lifted)):
            facts.append(f"{callee_name}()의 결과를 그대로 반환한다." if local == root else f"{callee_name}()의 결과를 익명 함수의 반환값으로 돌려준다.")
        elif parent is not None and parent.type == "expression_statement":
            facts.append(f"{callee_name}()의 반환값을 사용하지 않는다.")
        facts.extend(_use_facts(call, f"{callee_name}()의 결과", local))
        arguments = call.child_by_field_name("arguments")
        args = [text(argument) for argument in arguments.named_children if argument.type != "comment"]
        if method == "apply":
            if len(args) > 1:
                facts.append(f"{args[1]}를 인자 목록으로 전달한다.")
            continue
        # fn.call(this, ...)의 첫 인자는 this이다.
        args = args[1:] if method == "call" else args
        if args:
            facts.append(f"{', '.join(args)}를 인자로 전달한다.")
    return list(dict.fromkeys(facts))

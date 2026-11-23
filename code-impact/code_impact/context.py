from pathlib import Path
from typing import TypeVar

from .models import Function, ImpactNode, SourceNotFound

T = TypeVar("T", bound=Function)


def read_context(nodes: list[T]) -> list[T]:
    cache: dict[Path, bytes] = {}
    for node in nodes:
        path = Path(node.path or node.file)
        if path not in cache:
            try:
                cache[path] = path.read_bytes()
                cache[path].decode("utf-8")
            except (OSError, UnicodeError):
                raise SourceNotFound() from None
        content = cache[path]
        if node.node is not None:
            source = content[node.node.start_byte:node.node.end_byte].decode("utf-8")
            node.start_line = node.node.start_point.row + 1
            node.end_line = node.node.end_point.row + 1
        else:
            lines = content.decode("utf-8").splitlines(keepends=True)
            if not 1 <= node.start_line <= node.end_line <= len(lines):
                raise SourceNotFound("함수의 코드 위치를 확인할 수 없습니다.")
            source = "".join(lines[node.start_line - 1:node.end_line])
        node.source_truncated = node.end_line - node.start_line + 1 > 200
        if node.source_truncated:
            anchors = [call.line for call in node.calls] if isinstance(node, ImpactNode) else []
            if not anchors:
                anchors = [node.start_line, node.end_line]
            spans: list[tuple[int, int]] = []
            for anchor in sorted(anchors):
                start = max(node.start_line, anchor - 30) - node.start_line
                end = min(node.end_line, anchor + 30) - node.start_line + 1
                if spans and start <= spans[-1][1]:
                    spans[-1] = (spans[-1][0], max(spans[-1][1], end))
                else:
                    spans.append((start, end))
            lines = source.splitlines(keepends=True)
            source = "// ... 긴 함수의 일부 문맥만 표시합니다 ...\n" + "\n// ... 생략 ...\n".join(
                "".join(lines[start:end]) for start, end in spans
            )
        node.source = source
    return nodes

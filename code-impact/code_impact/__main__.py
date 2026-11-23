from __future__ import annotations

import argparse
import json
import logging
import sys
from collections.abc import Sequence

from .formatter import to_json
from .model import Model
from .models import CodeImpactError, SourceNotFound
from .orchestrator import analyze


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        # 외부 계약의 에러 코드 네 개를 유지하며 누락/부적합 입력을 안내한다.
        raise SourceNotFound("분석할 파일, 프로젝트 루트, 커서 위치와 탐색 깊이 인자를 확인해야 합니다.")


def main(argv: Sequence[str] | None = None, *, model: Model | None = None) -> int:
    logging.basicConfig(stream=sys.stderr, level=logging.WARNING)
    parser = _Parser(prog="code_impact")
    commands = parser.add_subparsers(dest="command", required=True)
    command = commands.add_parser("analyze")
    command.add_argument("--root", required=True)
    command.add_argument("--file", required=True)
    command.add_argument("--line", required=True, type=int)
    command.add_argument("--col", required=True, type=int)
    command.add_argument("--depth", type=int, default=3)
    try:
        args = parser.parse_args(argv)
        if args.depth < 1:
            parser.error("invalid depth")
        result = analyze(args.root, args.file, args.line, args.col, args.depth, model)
        output = to_json(result)
    except CodeImpactError as error:
        sys.stdout.write(json.dumps({"error": {"code": error.code, "message": str(error)}}, ensure_ascii=False) + "\n")
        return 1
    sys.stdout.write(output + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

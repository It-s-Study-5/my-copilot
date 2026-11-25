from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path

from .formatter import to_json
from .model import Model
from .models import CodeImpactError, SourceNotFound
from .models import AnalysisResult
from .orchestrator import analyze


def _write_log(args: argparse.Namespace, result: AnalysisResult) -> None:
    # 실행 기록을 JSON Lines로 쌓는다. logs/는 .gitignore 대상이다. 로그 실패가 분석 결과를 막지 않는다.
    path = Path(os.environ.get("CODE_IMPACT_LOG_FILE") or Path(__file__).resolve().parents[1] / "logs" / "trace.jsonl")
    entry = {
        "time": datetime.now().astimezone().isoformat(timespec="seconds"),
        "root": args.root, "file": args.file, "line": args.line, "col": args.col,
        "target": result.target.name, "trace": result.trace, "warnings": result.warnings,
    }
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as log:
            log.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError:
        logging.warning("실행 기록 로그를 쓸 수 없습니다: %s", path)


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
        _write_log(args, result)
    except CodeImpactError as error:
        sys.stdout.write(json.dumps({"error": {"code": error.code, "message": str(error)}}, ensure_ascii=False) + "\n")
        return 1
    sys.stdout.write(output + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

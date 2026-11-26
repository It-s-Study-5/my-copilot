"""Conduit demo commit gate. Run from a trusted local application checkout."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

from conduit_probe import check
from staged_slop import scan
from slop_agent import review, review_paths
from review_edits import working_tree_snapshot
from user_report import render


def git(root, *args):
    return subprocess.check_output(
        ["git", "-C", str(root), *args], stderr=subprocess.PIPE
    ).decode().strip()


def evaluate(root, request):
    findings = []
    checks = {}
    try:
        findings = scan(root)
        checks["debug_traces"] = {"status": "fail" if findings else "pass"}
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as err:
        checks["debug_traces"] = {"status": "unchecked", "details": str(err)}
    try:
        checks["article_title"] = check(root)
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as err:
        checks["article_title"] = {"status": "unchecked", "details": str(err)}

    if sys.stderr.isatty():
        print("글 작성 동작을 확인하고 변경 코드를 검토하고 있어요…", file=sys.stderr, flush=True)
    agent = review(root, request)
    agent["provider"] = "OpenAI API" if os.getenv("OPENAI_API_KEY") else "Codex CLI"
    states = [result["status"] for result in checks.values()] + [agent["status"]]
    if "fail" in states:
        status = "fail"
    elif all(state == "pass" for state in states):
        status = "pass"
    else:
        status = "unchecked"
    feedback = []
    if findings:
        feedback.append("표시된 줄의 디버그 흔적을 확인하고 불필요한 출력을 정리해 주세요.")
    if checks["article_title"]["status"] == "fail":
        feedback.append("게시글 생성 검사에서 기대값과 다른 입력을 확인하고 해당 처리를 수정해 주세요.")
    if "unchecked" in states:
        feedback.append("실행하지 못한 검사의 원인을 확인한 뒤 다시 시도해 주세요.")
    return dict(status=status, checks=checks, agent=agent, findings=findings, feedback=feedback,
                untested=["브라우저 화면", "실제 HTTP 연결과 DB 저장"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("question", nargs="?", help="바뀐 작업 파일에 대해 코파일럿에 물어볼 질문")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--working", action="store_true", help="커밋 전 미리보기. 현재 작업 파일의 추적 중인 변경을 검사합니다.")
    parser.add_argument("--request", default=os.getenv("AI_SLOP_REQUEST"),
                        help="코파일럿에 요청한 작업 내용. 생략하면 변경 자체를 검토합니다.")
    parser.add_argument("--hook", action="store_true", help="자동 커밋 검사. 대상 변경이 없으면 건너뜁니다.")
    output = parser.add_mutually_exclusive_group()
    output.add_argument("--json", action="store_true")
    output.add_argument("--prompt", action="store_true", help="채팅에 복사할 검사 근거와 요청을 출력합니다.")
    args = parser.parse_args()
    preview = bool(args.question) or args.working
    try:
        root = Path(git(args.root, "rev-parse", "--show-toplevel"))
        original_tree = git(root, "write-tree")
        tree = working_tree_snapshot(root, original_tree) if preview else original_tree
        with tempfile.TemporaryDirectory() as directory:
            # Preserve Git's selected index (including a partial commit), then
            # make every child read the exact same immutable tree.
            original = os.environ.get("GIT_INDEX_FILE")
            os.environ["GIT_INDEX_FILE"] = str(Path(directory) / "index")
            try:
                git(root, "read-tree", tree)
                if args.hook and not review_paths(root):
                    result = {"status": "skipped", "reason": "검사 대상인 제품 JS/TS 변경이 없어 커밋 검사를 건너뛰었어요."}
                else:
                    result = evaluate(root, args.question or args.request or "이번 변경에서 구현 누락이나 불필요하게 추가된 코드를 확인해 주세요.")
            finally:
                if original is None:
                    del os.environ["GIT_INDEX_FILE"]
                else:
                    os.environ["GIT_INDEX_FILE"] = original
        result["tree"] = tree
        if git(root, "write-tree") != original_tree:
            result = dict(status="unchecked", tree=tree,
                          error="검사 중 스테이징 내용이 바뀌었습니다. 현재 변경으로 다시 검사해 주세요.")
    except (OSError, subprocess.SubprocessError, UnicodeError) as err:
        result = dict(status="unchecked", error=f"Git 스테이징 상태를 읽지 못했습니다 ({err})")
    if args.json:
        print(json.dumps(result, ensure_ascii=False))
    else:
        print(render(result, prompt=args.prompt))
        if preview and not args.prompt:
            print("\nGit이 추적 중인 작업 파일을 확인했어요.")
    return {"pass": 0, "skipped": 0, "fail": 1, "unchecked": 2}[result["status"]]


if __name__ == "__main__":
    sys.exit(main())

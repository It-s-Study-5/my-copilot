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


def git(root, *args):
    return subprocess.check_output(
        ["git", "-C", str(root), *args], stderr=subprocess.PIPE
    ).decode().strip()


def evaluate(root):
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

    states = [result["status"] for result in checks.values()]
    if "fail" in states:
        status = "fail"
    elif states == ["pass", "pass"]:
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
    return dict(status=status, checks=checks, findings=findings, feedback=feedback,
                untested=["브라우저 화면", "실제 HTTP 연결과 DB 저장"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        root = Path(git(args.root, "rev-parse", "--show-toplevel"))
        tree = git(root, "write-tree")
        with tempfile.TemporaryDirectory() as directory:
            # Preserve Git's selected index (including a partial commit), then
            # make every child read the exact same immutable tree.
            original = os.environ.get("GIT_INDEX_FILE")
            os.environ["GIT_INDEX_FILE"] = str(Path(directory) / "index")
            try:
                git(root, "read-tree", tree)
                result = evaluate(root)
            finally:
                if original is None:
                    del os.environ["GIT_INDEX_FILE"]
                else:
                    os.environ["GIT_INDEX_FILE"] = original
        result["tree"] = tree
    except (OSError, subprocess.SubprocessError) as err:
        result = dict(status="unchecked", error=f"Git 스테이징 상태를 읽지 못했습니다 ({err})")
    if args.json:
        print(json.dumps(result, ensure_ascii=False))
    else:
        print(f"AI Slop | {result['status'].upper()}")
        for item in result.get("findings", []):
            print(f"  {item['path']}:{item['line']}  {item['message']}")
        for name, item in result.get("checks", {}).items():
            print(f"  {name}: {item['status'].upper()}")
            details = item.get("details")
            if isinstance(details, dict):
                for case in details.get("cases", []):
                    actual = case["actual"]
                    title = json.dumps(case["input"], ensure_ascii=False)
                    print(f"    제목 {title}  {case['status'].upper()}  기대 {case['expected']}"
                          f" / 실제 응답 {actual['response']}, 생성 호출 {actual['modelCreateCalls']}회")
                if details.get("reason"):
                    print("   ", details["reason"])
            elif details:
                print("   ", details)
        if "error" in result:
            print(result["error"])
        for statement in result.get("feedback", []):
            print(statement)
        if "untested" in result:
            print("미확인:", ", ".join(result["untested"]))
    return {"pass": 0, "fail": 1, "unchecked": 2}[result["status"]]


if __name__ == "__main__":
    sys.exit(main())

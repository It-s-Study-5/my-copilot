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
from slop_agent import review


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
        print("모델이 staged 변경을 검토하고 있습니다…", file=sys.stderr, flush=True)
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
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--request", default=os.getenv("AI_SLOP_REQUEST"),
                        help="코파일럿에 요청한 작업 내용. 생략하면 변경 자체를 검토합니다.")
    output = parser.add_mutually_exclusive_group()
    output.add_argument("--json", action="store_true")
    output.add_argument("--prompt", action="store_true", help="채팅에 복사할 검사 근거와 요청을 출력합니다.")
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
                result = evaluate(root, args.request or "이번 변경에서 구현 누락이나 불필요하게 추가된 코드를 확인해 주세요.")
            finally:
                if original is None:
                    del os.environ["GIT_INDEX_FILE"]
                else:
                    os.environ["GIT_INDEX_FILE"] = original
        result["tree"] = tree
        if git(root, "write-tree") != tree:
            result = dict(status="unchecked", tree=tree,
                          error="검사 중 스테이징 내용이 바뀌었습니다. 현재 변경으로 다시 검사해 주세요.")
    except (OSError, subprocess.SubprocessError) as err:
        result = dict(status="unchecked", error=f"Git 스테이징 상태를 읽지 못했습니다 ({err})")
    if args.json:
        print(json.dumps(result, ensure_ascii=False))
    else:
        if args.prompt:
            print({
                "fail": "다음 검사에서 확인된 문제를 수정해 주세요. 수정 후 같은 조건으로 다시 확인할게요.",
                "unchecked": "검사를 끝내지 못했어요. 아래 원인을 확인하고 다시 검사할 수 있게 도와주세요.",
                "pass": "이번에 실행한 검사는 모두 통과했어요.",
            }[result["status"]])
            if "tree" in result:
                print("검사한 Git tree:", result["tree"])
        else:
            print(f"AI Slop | {result['status'].upper()}")
        agent = result.get("agent", {})
        if agent:
            print(f"모델 검토 ({agent['provider']})")
            for key, label in (("hypothesis", "확인할 점"), ("tool", "선택한 도구"),
                               ("feedback", "검토 의견"), ("reason", "미확인 사유")):
                if agent.get(key):
                    print(f"  {label}: {agent[key]}")
            if agent.get("tool") == "staged_symbol":
                for match in agent.get("evidence", {}).get("matches", []):
                    print(f"    {match['path']}:{match['line']}  {match['source']}")
        for item in result.get("findings", []):
            print(f"  {item['path']}:{item['line']}  {item['message']}")
        for name, item in result.get("checks", {}).items():
            if args.prompt and item["status"] == "pass":
                continue
            print(f"  {name}: {item['status'].upper()}")
            details = item.get("details")
            if isinstance(details, dict):
                for case in details.get("cases", []):
                    if args.prompt and case["status"] == "pass":
                        continue
                    actual = case["actual"]
                    title = json.dumps(case["input"], ensure_ascii=False)
                    if "error" in actual:
                        print(f"    제목 {title}  {case['status'].upper()}  {actual['error']}")
                        continue
                    print(f"    제목 {title}  {case['status'].upper()}  기대 {case['expected']}"
                          f" / 실제 응답 {actual['response']}, 생성 호출 {actual['modelCreateCalls']}회")
                if details.get("reason"):
                    print("   ", details["reason"])
            elif details:
                print("   ", details)
        if "error" in result:
            print(result["error"])
        if not args.prompt:
            for statement in result.get("feedback", []):
                print(statement)
        if "untested" in result:
            print("미확인:", ", ".join(result["untested"]))
    return {"pass": 0, "fail": 1, "unchecked": 2}[result["status"]]


if __name__ == "__main__":
    sys.exit(main())

"""Human-readable view of a single gate run. JSON remains the integration contract."""
import re


def _label(title):
    if not title:
        return "빈 제목"
    if title.isspace():
        return "공백만 있는 제목"
    return "일반 제목"


def _failure(case):
    title = _label(case["input"])
    actual = case["actual"]
    calls = actual.get("modelCreateCalls")
    if not case["input"].strip() and calls:
        return f"{title}으로도 서버가 글 생성을 시도했어요."
    if case["input"].strip() and calls == 0:
        return "일반 제목을 보냈는데 서버가 글 생성을 시작하지 않았어요."
    return f"{title}을 검사했을 때 예상과 다른 결과가 나왔어요."


def _observed(case):
    actual = case["actual"]
    return (f"{_label(case['input'])} 검사에서 기대한 값은 {case['expected']}, "
            f"실제 응답은 {actual.get('response')}, 생성 호출은 {actual.get('modelCreateCalls')}회였어요.")


def _short(text, limit=180):
    # Keep the first complete thought when the model returned multiple paragraphs.
    sentences = re.split(r"(?<=[.!?])\s+|\n", text.strip())
    first = next((sentence for sentence in sentences if len(sentence.strip()) >= 8), "")
    return first if len(first) <= limit else first[:limit - 1] + "…"


def render(result, *, prompt=False):
    status = result["status"]
    checks = result.get("checks", {})
    article = checks.get("article_title", {})
    details = article.get("details", {})
    cases = details.get("cases", []) if isinstance(details, dict) else []
    failed = [case for case in cases if case["status"] == "fail"]
    findings = result.get("findings", [])
    agent = result.get("agent", {})
    unknown = [result["error"]] if result.get("error") else []
    for check in checks.values():
        check_details = check.get("details", {})
        if check["status"] == "unchecked":
            reason = check_details.get("reason") if isinstance(check_details, dict) else check_details
            if reason:
                unknown.append(str(reason))
    for case in cases:
        if case["status"] == "unchecked":
            unknown.append(f"{_label(case['input'])} 검사 — " +
                           case["actual"].get("error", "응답을 판정하지 못했어요."))
    if agent.get("reason"):
        unknown.append(agent["reason"])

    if failed:
        summary = _failure(failed[0])
    elif findings:
        summary = "브라우저 코드에 디버그 문장이 남아 있어요."
    elif status == "unchecked":
        summary = "검사를 마치지 못했어요. 아래 원인을 확인하고 다시 실행해 주세요."
    elif status == "pass":
        passed = {_label(c["input"]) for c in cases if c["status"] == "pass"}
        if {"공백만 있는 제목", "일반 제목"} <= passed:
            summary = "글 생성 검사에서 공백 제목은 거부됐고 일반 제목은 통과했어요."
        else:
            summary = "이번에 실행한 검사를 통과했어요."
    else:
        summary = "게시글 변경 사항을 다시 확인해야 해요."

    lines = [summary]
    for case in failed:
        lines.append(_observed(case))
    if unknown:
        lines.append("미확인 사유 — " + " / ".join(dict.fromkeys(unknown)))
    if agent.get("status") == "pass" and agent.get("feedback") and status != "unchecked":
        insight = _short(agent["feedback"])
        if insight:
            lines.append("AI 검토 의견 — " + insight)
    if result.get("untested"):
        lines.append("확인하지 않은 범위 — " + ", ".join(result["untested"]))

    actions = []
    if any(not c["input"].strip() for c in failed):
        actions.append("빈 제목과 공백 제목은 글 생성 전에 거부하도록 고쳐줘.")
    if any(c["input"].strip() for c in failed):
        actions.append("일반 제목으로 글을 생성할 수 있게 고쳐줘.")
    if findings:
        locations = ", ".join(f"{f['path']}:{f['line']}" for f in findings[:3])
        extra = f" 외 {len(findings) - 3}곳" if len(findings) > 3 else ""
        actions.append(f"{locations}{extra}의 디버그 문장도 확인해줘.")
    if actions:
        request = " ".join(actions) + " 수정한 뒤 같은 조건으로 다시 확인해줘."
        if prompt:
            lines.insert(0, request)
        else:
            lines.extend(["", "코파일럿에 보낼 요청", request])
    return "\n".join(lines)

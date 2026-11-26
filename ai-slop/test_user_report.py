import unittest

from user_report import render


def outcome(status, cases, **kw):
    return dict(status=status, checks={"article_title": {"status": status, "details": {"cases": cases}}},
                untested=["브라우저 화면", "실제 HTTP 연결과 DB 저장"], **kw)


def case(title, status, code, calls):
    return dict(input=title, status=status, expected="400 또는 422, 생성 0회" if not title.strip() else "201, 생성 1회",
                actual={"response": code, "modelCreateCalls": calls})


class UserReportTests(unittest.TestCase):
    def test_fail_starts_with_observed_impact_and_has_single_ready_request(self):
        result = outcome("fail", [case("   ", "fail", 201, 1)],
                         findings=[{"path": "frontend/src/article.ts", "line": 4}],
                         agent={"status": "pass", "feedback": "네. 컨트롤러를 확인했어요. 긴 문단은 생략해요."})
        text = render(result)
        self.assertTrue(text.startswith("공백만 있는 제목으로도 서버가 글 생성을 시도했어요."))
        self.assertIn("실제 응답은 201, 생성 호출은 1회", text)
        self.assertIn("frontend/src/article.ts:4", text)
        self.assertEqual(text.count("코파일럿에 보낼 요청"), 1)
        self.assertIn("AI 검토 의견 — 컨트롤러를 확인했어요.", text)
        self.assertNotIn("긴 문단", text)
        self.assertIn("브라우저 화면", text)
        self.assertIn("고쳐줘", render(result, prompt=True).splitlines()[0])

    def test_success_only_claims_observed_cases(self):
        text = render(outcome("pass", [case("   ", "pass", 422, 0), case("hello", "pass", 201, 1)]))
        self.assertIn("공백 제목은 거부됐고 일반 제목은 통과", text)
        self.assertNotIn("코파일럿에 보낼 요청", text)
        self.assertNotIn("일반 제목", render(outcome("pass", [])))

    def test_unchecked_explains_error_without_ai_diagnosis(self):
        result = outcome("unchecked", [], error="스테이징 내용이 바뀌었습니다.",
                         agent={"status": "pass", "feedback": "예상 원인"})
        self.assertIn("스테이징 내용이 바뀌었습니다.", render(result))
        self.assertNotIn("예상 원인", render(result))
        self.assertNotIn("고쳐줘", render(result, prompt=True))

    def test_mixed_preserves_confirmed_failure_and_unchecked_reason(self):
        result = outcome("fail", [case("", "fail", 201, 1),
                                   dict(input="test", status="unchecked", actual={"error": "컨트롤러 실행 오류"})])
        self.assertIn("빈 제목으로도", render(result))
        self.assertIn("컨트롤러 실행 오류", render(result))

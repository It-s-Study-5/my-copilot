from contextlib import redirect_stdout
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import gate


class GateTests(unittest.TestCase):
    def setUp(self):
        mock_review = patch.object(gate, "review", return_value={"status": "pass", "feedback": "검토 완료"})
        self.review = mock_review.start()
        self.addCleanup(mock_review.stop)
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.root.joinpath("article").write_text("before")
        self.git("init", "-q")
        self.git("add", "article")

    def git(self, *args, env=None):
        return subprocess.check_output(["git", "-C", str(self.root), *args], env=env)

    def run_gate(self, *args):
        output = io.StringIO()
        with patch("sys.argv", ["gate.py", "--root", str(self.root), *args]), redirect_stdout(output):
            status = gate.main()
        return status, output.getvalue()

    def test_hook_skips_unrelated_change_without_touching_index_or_running_checks(self):
        with patch.object(gate, "check") as probe, patch.object(gate, "scan") as scan:
            before = self.git("write-tree")
            status, output = self.run_gate("--hook", "--json")
            self.assertEqual(status, 0)
            self.assertEqual(json.loads(output)["status"], "skipped")
            self.assertEqual(self.git("write-tree"), before)
            self.assertIn("건너뛰", self.run_gate("--hook")[1])
            self.review.assert_not_called()
            probe.assert_not_called()
            scan.assert_not_called()

    def test_hook_scope_lookup_error_blocks_commit(self):
        with patch.object(gate, "review_paths", side_effect=subprocess.CalledProcessError(1, "git")):
            status, output = self.run_gate("--hook", "--json")
        self.assertEqual(status, 2)
        self.assertEqual(json.loads(output)["status"], "unchecked")

    def test_document_only_and_empty_commit_with_real_hook(self):
        module = Path(gate.__file__).resolve()
        self.git("config", "core.hooksPath", str(module.parent))
        self.git("config", "aiSlop.gate", str(module))
        for name, value in (("user.name", "QA"), ("user.email", "qa@example.invalid"),
                            ("commit.gpgsign", "false")):
            self.git("config", name, value)
        self.root.joinpath("README.md").write_text("docs")
        self.git("add", "README.md")
        for cmd in (["commit", "-m", "docs"], ["commit", "--allow-empty", "-m", "empty"]):
            proc = subprocess.run(["git", "-C", str(self.root), *cmd], capture_output=True, text=True)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertIn("건너뛰", proc.stderr)
        self.assertEqual(self.git("rev-list", "--count", "HEAD").strip(), b"2")

    def test_question_reviews_current_edits_but_commit_uses_index(self):
        source = self.root / "backend" / "sample.js"
        source.parent.mkdir()
        source.write_text("staged")
        self.git("add", "backend")
        source.write_text("edited")
        observed = []

        def inspect(root, request):
            observed.append((self.git("show", ":backend/sample.js"), request))
            return {"status": "pass"}

        self.review.side_effect = inspect
        with patch.object(gate, "check", return_value={"status": "pass"}):
            preview_status, _ = self.run_gate("지금 수정한 코드 확인해줘")
            hook_status, _ = self.run_gate("--request", "커밋할 코드 확인해줘")
        self.assertEqual((preview_status, hook_status), (0, 0))
        self.assertEqual(observed, [(b"edited", "지금 수정한 코드 확인해줘"), (b"staged", "커밋할 코드 확인해줘")])
        self.assertEqual(self.git("show", ":backend/sample.js"), b"staged")

    def test_model_failure_is_visible_and_blocks_otherwise_passing_commit(self):
        self.review.return_value = {"status": "unchecked", "reason": "모델 연결 실패"}
        with patch.object(gate, "check", return_value={"status": "pass"}):
            status, output = self.run_gate("--request", "제목 검사")
        self.assertEqual(status, 2)
        self.assertIn("모델 연결 실패", output)
        self.assertEqual(self.review.call_args.args[1], "제목 검사")

    def test_index_changed_during_checks_requires_recheck(self):
        original_env = os.environ.copy()
        before = self.git("write-tree").decode().strip()

        def stage_new_version(root):
            root.joinpath("article").write_text("after")
            self.git("add", "article", env=original_env)
            self.assertEqual(self.git("show", ":article"), b"before")
            return {"status": "pass"}

        with patch.object(gate, "check", side_effect=stage_new_version):
            status, output = self.run_gate("--json")
        result = json.loads(output)
        self.assertEqual(status, 2)
        self.assertEqual(result["status"], "unchecked")
        self.assertEqual(result["tree"], before)
        self.assertIn("다시 검사", result["error"])
        self.assertEqual(self.git("show", ":article"), b"after")

    def test_console_displays_controller_exception(self):
        case = {"input": "", "expected": "422", "status": "unchecked",
                "actual": {"error": "컨트롤러 실행 오류"}}
        with patch.object(gate, "check", return_value={"status": "unchecked", "details": {"cases": [case]}}):
            status, output = self.run_gate()
        self.assertEqual(status, 2)
        self.assertIn("검사를 마치지 못했어요", output)
        self.assertIn("컨트롤러 실행 오류", output)

    def test_chat_prompt_contains_failed_evidence_and_scope(self):
        cases = [
            {"input": "   ", "expected": "422", "actual": {"response": 201, "modelCreateCalls": 1},
             "status": "fail"},
            {"input": "정상 제목", "expected": "201", "actual": {"response": 201, "modelCreateCalls": 1},
             "status": "pass"},
        ]
        finding = {"path": "frontend/src/a.js", "line": 4, "message": "디버그 출력"}
        with patch.object(gate, "scan", return_value=[finding]), patch.object(
            gate, "check", return_value={"status": "fail", "details": {"cases": cases}}
        ):
            status, output = self.run_gate("--prompt")
        self.assertEqual(status, 1)
        for evidence in ("공백만 있는 제목", "기대한 값은 422", "실제 응답은 201", "생성 호출은 1회",
                         "frontend/src/a.js:4", "브라우저 화면"):
            self.assertIn(evidence, output)
        self.assertNotIn("정상 제목", output)

    def test_chat_prompt_for_pass_and_unavailable_probe(self):
        with patch.object(gate, "check", return_value={"status": "pass"}):
            status, output = self.run_gate("--prompt")
        self.assertEqual(status, 0)
        self.assertIn("통과", output)
        self.assertNotIn("수정해", output)
        with patch.object(gate, "check", return_value={"status": "unchecked", "details": {"reason": "Node 누락"}}):
            status, output = self.run_gate("--prompt")
        self.assertEqual(status, 2)
        self.assertIn("Node 누락", output)
        self.assertNotIn("통과", output)

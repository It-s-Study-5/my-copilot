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
        self.assertIn("UNCHECKED  컨트롤러 실행 오류", output)

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
        for evidence in ('제목 "   "', "기대 422", "실제 응답 201", "생성 호출 1회",
                         "frontend/src/a.js:4", "브라우저 화면", self.git("write-tree").decode().strip()):
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

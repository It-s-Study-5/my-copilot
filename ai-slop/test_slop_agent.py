from pathlib import Path
import json
import subprocess
import tempfile
import unittest
from unittest.mock import Mock

from model_client import ModelError
from slop_agent import review


class SlopAgentTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.git("init", "-q")
        self.source = "frontend/src/article.js"
        self.stage(self.source, "export function saveTitle() { return true; }")

    def git(self, *args):
        subprocess.run(["git", "-C", str(self.root), *args], capture_output=True, check=True)

    def stage(self, path, source):
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(source)
        self.git("add", "--", path)

    def test_model_selects_tool_and_receives_actual_staged_evidence(self):
        self.stage("backend/config/key.js", "HIDDEN CONFIG")
        self.stage("frontend/src/article.test.js", "HIDDEN TEST saveTitle")
        (self.root / self.source).write_text("WORKTREE_ONLY")
        model = Mock(side_effect=[
            {"hypothesis": "중복 정의가 있을 수 있다.", "tool": "staged_symbol", "symbol": "saveTitle"},
            {"feedback": "선언 한 곳을 찾았습니다. 중복은 확인되지 않았습니다."},
        ])
        result = review(self.root, "제목을 저장해줘", ask_model=model)
        self.assertEqual(result["status"], "pass", result)
        first, second = (call.args[0] for call in model.call_args_list)
        for text in (first, second):
            self.assertNotIn("WORKTREE_ONLY", text)
            self.assertNotIn("HIDDEN", text)
            self.assertIn("제목을 저장해줘", text)
        evidence = result["evidence"]
        self.assertEqual([(m["path"], m["line"]) for m in evidence["matches"]], [(self.source, 1)])
        self.assertEqual(json.loads(second.splitlines()[-1])["evidence"], evidence)

    def test_rejects_command_like_argument(self):
        model = Mock(return_value={"hypothesis": "확인", "tool": "staged_symbol", "symbol": "../.env"})
        self.assertEqual(review(self.root, "inspect", ask_model=model)["status"], "unchecked")
        self.assertEqual(model.call_count, 1)

    def test_stops_before_sending_obvious_credentials(self):
        self.stage(self.source, 'const password = "example-literal-value";')
        model = Mock()
        result = review(self.root, "inspect", ask_model=model)
        self.assertEqual(result["status"], "unchecked")
        self.assertNotIn("example-literal-value", str(result))
        model.assert_not_called()

    def test_model_failure_keeps_tool_result(self):
        model = Mock(side_effect=[{"hypothesis":"확인","tool":"debug_traces","symbol":""},
                                  ModelError("연결이 실패했습니다.")])
        self.stage(self.source, 'console.log("test");')
        result = review(self.root, "inspect", ask_model=model)
        self.assertEqual(result["status"], "unchecked")
        self.assertEqual(result["evidence"]["count"], 1)
        self.assertIn("연결", result["reason"])

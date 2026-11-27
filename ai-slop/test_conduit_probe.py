from pathlib import Path
import subprocess
import tempfile
import unittest

from conduit_probe import check


CONTROLLER = """
const { Article } = require("../models");
exports.createArticle = async (req, res) => {
  const title = req.body.article.title;
  if (!title) return res.status(422).json({});
  await Article.create({title});
  res.status(201).json({});
};
"""


class TestConduitProbe(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.git("init", "-q")
        for filename, source in {
            "controllers/articles.js": CONTROLLER,
            "helper/customErrors.js": "",
            "helper/helpers.js": "",
            "middleware/errorHandler.js": "module.exports = () => {};",
        }.items():
            path = self.root / "backend" / filename
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(source)
        self.controller = self.root / "backend/controllers/articles.js"
        self.git("add", "backend")

    def git(self, *args):
        subprocess.run(["git", "-C", str(self.root), *args], check=True, capture_output=True)

    def test_reads_staged_controller_even_when_worktree_fixed(self):
        self.controller.write_text(CONTROLLER.replace("!title", "!title.trim()"))
        before = check(self.root)
        self.assertEqual(before["status"], "fail")
        self.assertEqual(before["details"]["cases"][1]["actual"],
                         {"response": 201, "modelCreateCalls": 1})
        self.assertEqual(check(self.root), before)
        self.git("add", "backend")
        self.assertEqual(check(self.root)["status"], "pass")

    def test_reject_everything_fails_normal_title_control(self):
        self.controller.write_text(CONTROLLER.replace("!title", "true"))
        self.git("add", "backend")
        result = check(self.root)
        self.assertEqual(result["status"], "fail")
        self.assertEqual(result["details"]["cases"][-1]["status"], "fail")

    def test_failure_kept_when_another_case_is_unchecked(self):
        self.controller.write_text(CONTROLLER.replace(
            "if (!title) return res.status(422).json({});", "if (!title) throw new Error();"
        ))
        self.git("add", "backend")
        result = check(self.root)
        self.assertEqual(result["status"], "fail")
        self.assertEqual([case["status"] for case in result["details"]["cases"]],
                         ["unchecked", "fail", "pass"])

    def test_execution_errors_are_unchecked(self):
        self.controller.write_text("throw new Error('unavailable');")
        self.git("add", "backend")
        self.assertEqual(check(self.root)["status"], "unchecked")

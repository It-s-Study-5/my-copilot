import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from review_edits import working_tree_snapshot


class PreviewTreeTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.git("init", "-q")

    def git(self, *args):
        return subprocess.check_output(["git", "-C", str(self.root), *args]).decode().strip()

    def write(self, path, text):
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text)

    def test_working_changes_and_delete_appear_only_in_snapshot(self):
        self.write("frontend/src/app.js", "staged")
        self.write("backend/new-file.js", "new staged")
        self.write("backend/removed.js", "gone")
        self.write("docs/demo", "outside")
        self.git("add", ".")
        original = self.git("write-tree")
        self.write("frontend/src/app.js", "working")
        self.write("backend/new-file.js", "new working")
        (self.root / "backend/removed.js").unlink()
        self.write("docs/demo", "ignored change")
        self.write("backend/.env", "private")
        self.write("frontend/src/new.js", "untracked")
        before = self.git("status", "--porcelain")
        snapshot = working_tree_snapshot(self.root, original)
        self.assertEqual(self.git("show", snapshot + ":frontend/src/app.js"), "working")
        self.assertEqual(self.git("show", snapshot + ":backend/new-file.js"), "new working")
        self.assertEqual(self.git("show", snapshot + ":docs/demo"), "outside")
        self.assertEqual(set(self.git("ls-tree", "-r", "--name-only", snapshot).splitlines()),
                         {"frontend/src/app.js", "backend/new-file.js", "docs/demo"})
        self.assertEqual(self.git("write-tree"), original)
        self.assertEqual(self.git("status", "--porcelain"), before)

    def test_absent_roots_and_existing_alternate_index(self):
        self.write("backend/file.js", "before")
        self.git("add", "backend")
        initial_tree = self.git("write-tree")
        custom_index = str(self.root / ".git/custom-index")
        with patch.dict(os.environ, {"GIT_INDEX_FILE": custom_index}):
            self.git("read-tree", initial_tree)
            self.write("backend/file.js", "after")
            snapshot = working_tree_snapshot(self.root, initial_tree)
            self.assertEqual(self.git("show", snapshot + ":backend/file.js"), "after")
            self.assertEqual(self.git("show", ":backend/file.js"), "before")
            with self.assertRaises(subprocess.CalledProcessError):
                working_tree_snapshot(self.root, "0000000000000000000000000000000000000000")
            self.assertEqual(self.git("write-tree"), initial_tree)
        self.assertEqual(self.git("write-tree"), initial_tree)

"""Build a temporary Git tree for reviewing edits before staging."""
import os
from pathlib import Path
import subprocess
import tempfile


def working_tree_snapshot(root: Path, initial_tree: str) -> str:
    """Overlay tracked Conduit edits on initial_tree without updating the caller's index."""
    with tempfile.TemporaryDirectory(prefix="slop-edits-") as directory:
        env = dict(os.environ, GIT_INDEX_FILE=str(Path(directory) / "index"))

        def git(*args):
            return subprocess.check_output(
                ["git", "--literal-pathspecs", "-C", str(root), *args],
                env=env, stderr=subprocess.PIPE,
            )

        git("read-tree", initial_tree)
        for path in ("frontend/src", "backend"):
            # A demo checkout can contain only one side. Git add rejects an
            # unmatched path, but also needs to see paths deleted on disk.
            if git("ls-files", "-z", "--", path):
                git("add", "--update", "--", path)
        return git("write-tree").decode("ascii").strip()

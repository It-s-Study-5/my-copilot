import json
import subprocess
import sys
from pathlib import Path

import pytest

PROJECT = Path(__file__).resolve().parents[1]
BOOTSTRAP = """import sys
from code_impact.__main__ import main
from code_impact.model import FakeModel
raise SystemExit(main(model=FakeModel(sys.stdin.read())))
"""


def cli(root: Path, file: Path, line: int = 2, col: int = 2, *, fake: bool = True):
    args = [sys.executable, "-c", BOOTSTRAP] if fake else [sys.executable, "-m", "code_impact"]
    args += ["analyze", "--root", str(root), "--file", str(file), "--line", str(line), "--col", str(col)]
    return subprocess.run(args, cwd=PROJECT, input=json.dumps({
        "summary": "계산 결과가 연결됩니다. 사용 방식을 확인해야 합니다.",
        "impacts": [],
    }), capture_output=True, text=True, timeout=20)


def test_cli_success_with_injected_fake(fixtures_dir: Path) -> None:
    process = cli(fixtures_dir, fixtures_dir / "price.js")
    assert process.returncode == 0 and process.stderr == ""
    data = json.loads(process.stdout)
    assert set(data) == {"target", "summary", "impacts", "truncated", "warnings"}
    assert data["target"] == {"name": "calculatePrice", "file": "price.js", "start_line": 2, "end_line": 5}
    assert {(node["name"], node["depth"], node["relation"]) for node in data["impacts"]} == {
        ("preparePayment", 1, "direct"), ("createOrder", 1, "direct"), ("handleOrderRequest", 2, "indirect"),
    }
    order = next(node for node in data["impacts"] if node["name"] == "createOrder")
    assert "amount를 조건문(amount <= 0)에서 검사한다." in order["facts"]
    assert all(set(call) == {"callee", "line", "col"} for node in data["impacts"] for call in node["calls"])


@pytest.mark.parametrize(("file", "line", "code"), [
    ("price.js", 0, "NOT_IN_FUNCTION"), ("missing.js", 2, "FILE_NOT_FOUND"),
])
def test_cli_errors(fixtures_dir: Path, file: str, line: int, code: str) -> None:
    process = cli(fixtures_dir, fixtures_dir / file, line, fake=False)
    assert process.returncode == 1
    data = json.loads(process.stdout)
    assert data["error"]["code"] == code and isinstance(data["error"]["message"], str)
    assert process.stderr == ""


def test_module_entrypoint_without_provider(fixtures_dir: Path) -> None:
    process = cli(fixtures_dir, fixtures_dir / "price.js", fake=False)
    assert process.returncode == 0
    data = json.loads(process.stdout)
    assert data["summary"] is None and data["warnings"] and len(data["impacts"]) == 3


def test_cli_rejects_root_escape(fixtures_dir: Path, tmp_path: Path) -> None:
    process = cli(tmp_path, fixtures_dir / "price.js", fake=False)
    assert process.returncode == 1 and json.loads(process.stdout)["error"]["code"] == "FILE_NOT_FOUND"


def test_invalid_cli_input_is_one_error_json() -> None:
    process = subprocess.run([sys.executable, "-m", "code_impact", "analyze"], cwd=PROJECT, capture_output=True, text=True, timeout=20)
    assert process.returncode == 1 and process.stderr == ""
    assert json.loads(process.stdout)["error"]["code"] == "FILE_NOT_FOUND"

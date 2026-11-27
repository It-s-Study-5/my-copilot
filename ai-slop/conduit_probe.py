"""Run the Conduit createArticle controller against an in-memory model double."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile


MODULES = (
    "backend/controllers/articles.js",
    "backend/helper/customErrors.js",
    "backend/helper/helpers.js",
    "backend/middleware/errorHandler.js",
)
SCOPE = "스테이지된 createArticle 컨트롤러와 오류 처리기. 요청, 응답, DB 모델은 대역."


def check(root: Path) -> dict:
    details = {"scope": SCOPE, "cases": []}
    try:
        node = shutil.which("node")
        if not node:
            raise ValueError("Node.js 실행 파일을 찾지 못했습니다.")
        with tempfile.TemporaryDirectory(prefix="conduit-probe-") as directory:
            snapshot = Path(directory)
            for filename in MODULES:
                staged = subprocess.run(
                    ["git", "-C", str(root), "show", f":{filename}"],
                    capture_output=True, timeout=5,
                )
                if staged.returncode:
                    raise ValueError(f"스테이지된 파일을 읽을 수 없습니다: {filename}")
                target = snapshot / filename
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(staged.stdout)
            shutil.copyfile(Path(__file__).with_name("conduit_probe.cjs"), snapshot / "probe.cjs")
            result = subprocess.run(
                [node, "probe.cjs"], cwd=snapshot, env={"PATH": os.defpath},
                capture_output=True, timeout=8, check=False,
            )
            if result.returncode:
                raise ValueError("컨트롤러 또는 의존 모듈을 실행하지 못했습니다.")
            cases = json.loads(result.stdout)
            if not isinstance(cases, list) or len(cases) != 3:
                raise ValueError("검사 결과가 완전하지 않습니다.")
            details["cases"] = cases
            statuses = {case["status"] for case in cases}
            if "fail" in statuses:
                return {"status": "fail", "details": details}
            if "unchecked" in statuses:
                return {"status": "unchecked", "details": details}
            return {"status": "pass" if statuses == {"pass"} else "unchecked", "details": details}
    except (OSError, subprocess.TimeoutExpired, ValueError, KeyError, TypeError) as exc:
        details["reason"] = str(exc)
        return {"status": "unchecked", "details": details}

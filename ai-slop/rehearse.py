"""Rehearse the two commits in a disposable clone of the upstream Conduit demo."""
import argparse
from pathlib import Path
import subprocess
import tempfile

GATE_DIR = Path(__file__).resolve().parent


def run(root, *args, check=True):
    return subprocess.run(
        ["git", "-C", str(root), *args], capture_output=True, text=True, check=check
    )


def rehearse(source):
    with tempfile.TemporaryDirectory(prefix="slop-rehearsal-") as temp:
        root = Path(temp) / "conduit"
        run(temp, "clone", "--quiet", "--no-local", str(source), str(root))
        for name, value in (
            ("user.name", "Slop rehearsal"), ("user.email", "demo@example.invalid"),
            ("commit.gpgsign", "false"), ("core.hooksPath", str(GATE_DIR)),
            ("aiSlop.gate", str(GATE_DIR / "gate.py")),
        ):
            run(root, "config", "--local", name, value)
        frontend = root / "frontend/src/components/ArticleEditorForm/ArticleEditorForm.jsx"
        controller = root / "backend/controllers/articles.js"
        before = frontend.read_text()
        original = controller.read_text()
        if original.count("if (!title) throw") != 1:
            raise ValueError("이 리허설은 원본 Conduit 5e127d8의 제목 검사로 시작합니다.")
        frontend.write_text('console.log("article editor ready");\n' + before)
        run(root, "add", "--", str(frontend))
        head = run(root, "rev-parse", "HEAD").stdout
        index = run(root, "write-tree").stdout

        def blocked():
            commit = run(root, "commit", "-m", "demo: validate article title", check=False)
            output = commit.stdout + commit.stderr
            if "AI 검토 의견 — " not in output:
                raise RuntimeError("모델이 실제 검사 근거를 해석했는지 확인하지 못했습니다.\n" + output)
            if (commit.returncode == 0 or "공백만 있는 제목으로도 서버가 글 생성을 시도했어요." not in output
                    or f"{frontend.relative_to(root)}:1" not in output or "실제 응답은 201" not in output
                    or run(root, "rev-parse", "HEAD").stdout != head
                    or run(root, "write-tree").stdout != index):
                raise RuntimeError("예상한 차단 또는 index 보존을 확인하지 못했습니다.\n" + output)
            return output

        print(blocked(), end="")
        controller.write_text(original.replace("if (!title) throw", "if (!title?.trim()) throw"))
        frontend.write_text(before)
        blocked()
        print("작업 파일만 수정한 상태에서도 이전 index의 커밋이 차단됐습니다.")
        run(root, "add", "--", str(frontend), str(controller))
        commit = run(root, "commit", "-m", "demo: reject whitespace article title")
        output = commit.stdout + commit.stderr
        if "공백 제목은 거부됐고 일반 제목은 통과" not in output or run(root, "rev-parse", "HEAD").stdout == head:
            raise RuntimeError("PASS와 새 커밋을 확인하지 못했습니다.")
        print(output, end="")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("conduit", type=Path, help="기준 Conduit 로컬 저장소")
    rehearse(parser.parse_args().conduit.resolve())

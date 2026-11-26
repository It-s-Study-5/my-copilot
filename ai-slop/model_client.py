"""Structured model calls through OpenAI Chat Completions or the authenticated Codex CLI."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
from urllib import error, request


class ModelError(RuntimeError):
    """An actionable provider error safe to include in the gate report."""


def _openai(prompt: str, schema: dict, key: str) -> dict:
    payload = {
        "model": os.getenv("AI_SLOP_MODEL") or "gpt-4.1-mini",
        "messages": [{"role": "user", "content": prompt}],
        "response_format": {
            "type": "json_schema",
            "json_schema": {"name": "slop_review", "strict": True, "schema": schema},
        },
    }
    req = request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    )
    try:
        with request.urlopen(req, timeout=90) as response:
            envelope = json.load(response)
        answer = json.loads(envelope["choices"][0]["message"]["content"])
        if not isinstance(answer, dict):
            raise ValueError("expected object")
        return answer
    except error.HTTPError as exc:
        raise ModelError(f"OpenAI API 호출 실패 (HTTP {exc.code}). 키, 모델 또는 사용 한도를 확인해 주세요.") from None
    except OSError:
        raise ModelError("OpenAI API에 연결하지 못했습니다. 네트워크와 시간 제한을 확인해 주세요.") from None
    except (ValueError, TypeError, IndexError, KeyError):
        raise ModelError("OpenAI API의 구조화된 응답을 읽을 수 없습니다.") from None


def ask(prompt: str, schema: dict) -> dict:
    """Run a fresh model call. No shell command or repository path comes from the model."""
    if key := os.getenv("OPENAI_API_KEY"):
        return _openai(prompt, schema, key)
    with tempfile.TemporaryDirectory(prefix="slop-model-") as directory:
        schema_path = Path(directory) / "schema.json"
        answer_path = Path(directory) / "answer.json"
        schema_path.write_text(json.dumps(schema), encoding="utf-8")
        command = [
            "codex", "--ask-for-approval", "never", "exec", "--ephemeral",
            "--ignore-user-config", "--ignore-rules", "--skip-git-repo-check",
            "--sandbox", "read-only", "-c", 'web_search="disabled"',
            "-c", "project_doc_max_bytes=0",
            "--output-schema", str(schema_path), "--output-last-message", str(answer_path),
        ]
        for feature in ("apps", "plugins", "hooks", "multi_agent", "shell_tool", "unified_exec"):
            command.extend(["--disable", feature])
        if model := os.getenv("AI_SLOP_MODEL"):
            command.extend(["--model", model])
        command.append("-")
        try:
            subprocess.run(
                command, cwd=directory, input=prompt, encoding="utf-8",
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                timeout=90, check=True,
            )
        except FileNotFoundError as exc:
            raise ModelError("Codex CLI를 설치한 뒤 codex login을 실행해 주세요.") from exc
        except subprocess.TimeoutExpired as exc:
            raise ModelError("Codex 모델 응답이 90초 안에 도착하지 않았습니다.") from exc
        except (subprocess.CalledProcessError, OSError) as exc:
            raise ModelError("Codex 호출 실패. CLI 버전, 로그인 상태, 모델 접근 권한과 네트워크를 확인해 주세요.") from exc
        try:
            answer = json.loads(answer_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise ModelError("Codex의 JSON 응답을 읽을 수 없습니다.") from exc
        if not isinstance(answer, dict):
            raise ModelError("Codex 응답이 JSON 객체 형식이 아닙니다.")
        return answer

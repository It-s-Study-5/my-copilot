import io
import json
import os
from pathlib import Path
import subprocess
import unittest
from urllib.error import HTTPError
from unittest.mock import patch

from model_client import ModelError, ask


class ModelClientTest(unittest.TestCase):
    def setUp(self):
        env = patch.dict(os.environ, {"OPENAI_API_KEY": ""})
        env.start()
        self.addCleanup(env.stop)

    @patch("model_client.request.urlopen")
    def test_api_uses_schema_and_model(self, urlopen):
        body = {"choices": [{"message": {"content": '{"ok": true}'}}]}
        urlopen.return_value = io.BytesIO(json.dumps(body).encode())
        schema = {"type": "object"}
        with patch.dict(os.environ, OPENAI_API_KEY="fake-key", AI_SLOP_MODEL="test-model"):
            self.assertEqual(ask("staged change", schema), {"ok": True})
        req = urlopen.call_args.args[0]
        payload = json.loads(req.data)
        self.assertEqual(payload["model"], "test-model")
        self.assertEqual(payload["response_format"]["json_schema"]["schema"], schema)
        self.assertEqual(req.get_header("Authorization"), "Bearer fake-key")

    @patch("model_client.subprocess.run")
    @patch("model_client.request.urlopen", side_effect=HTTPError("", 401, "PRIVATE", None, None))
    def test_api_failure_does_not_retry_codex(self, urlopen, run):
        with patch.dict(os.environ, OPENAI_API_KEY="PRIVATE"):
            with self.assertRaisesRegex(ModelError, "401") as raised:
                ask("PRIVATE", {})
        self.assertNotIn("PRIVATE", str(raised.exception))
        run.assert_not_called()

    @patch("model_client.subprocess.run")
    def test_exec_uses_stdin_and_isolated_directory(self, run):
        schema = {"type": "object"}
        def answer(command, **kwargs):
            cwd = Path(kwargs["cwd"])
            self.assertNotEqual(cwd, Path.cwd())
            self.assertEqual(kwargs["input"], "review this change")
            self.assertNotIn(kwargs["input"], command)
            self.assertEqual(command[-1], "-")
            self.assertIn("--ignore-user-config", command)
            self.assertEqual(command[command.index("--model") + 1], "example-model")
            self.assertEqual(json.loads((cwd / "schema.json").read_text()), schema)
            (cwd / "answer.json").write_text('{"ok": true}')
        run.side_effect = answer
        with patch.dict(os.environ, AI_SLOP_MODEL="example-model"):
            self.assertEqual(ask("review this change", schema), {"ok": True})

    @patch("model_client.subprocess.run")
    def test_provider_errors_never_echo_prompt_or_cli_output(self, run):
        for error in (FileNotFoundError(), subprocess.TimeoutExpired("codex", 90),
                      subprocess.CalledProcessError(1, "codex", stderr="PRIVATE")):
            with self.subTest(error=type(error)):
                run.side_effect = error
                with self.assertRaises(ModelError) as raised:
                    ask("PRIVATE", {})
                self.assertNotIn("PRIVATE", str(raised.exception))

    @patch("model_client.subprocess.run")
    def test_malformed_answer(self, run):
        def answer(command, **kwargs):
            (Path(kwargs["cwd"]) / "answer.json").write_text("not json")
        run.side_effect = answer
        with self.assertRaises(ModelError):
            ask("check", {})

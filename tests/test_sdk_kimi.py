"""K3 profile and caller acceptance; every response is synthetic, zero network."""
import copy
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from model_api import ApiFailure, Backend, load_profile

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("kimi_smoke", ROOT / "scripts/kimi_api_smoke.py")
smoke = importlib.util.module_from_spec(spec)
spec.loader.exec_module(smoke)


class KimiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.folder = Path(self.tmp.name) / "attempt"
        self.request = json.loads(smoke.REQUEST.read_text())
        self.profile = load_profile(smoke.PROFILE)
        self.env = patch.dict(os.environ, {"MOONSHOT_API_KEY": "synthetic-kimi-credential"})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.calls = []

    def backend(self, *, status=200, response=None):
        if response is None:
            response = {
                "id": "synthetic-request", "model": "kimi-k3",
                "choices": [{"message": {"content": '{"status":"ok","count":0}',
                             "reasoning_content": "合成推理，不是最终答案"}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 0, "completion_tokens": 5, "total_tokens": 5,
                          "prompt_tokens_details": {"cached_tokens": 0},
                          "completion_tokens_details": {"reasoning_tokens": 3}},
            }
        def sender(url, body, headers, timeout):
            self.calls.append((url, json.loads(body), headers, timeout))
            return status, {"x-request-id": "synthetic-header-id"}, json.dumps(response).encode()
        return Backend(self.profile, sender=sender)

    def test_no_key_preflight_and_exact_wire(self):
        os.environ.pop("MOONSHOT_API_KEY")
        b = self.backend()
        report, code = smoke.run("preflight", backend=b)
        self.assertEqual(code, 0)
        self.assertEqual(report["network_requests"], 0)
        body = b.preflight(self.request)
        self.assertEqual(body["model"], "kimi-k3")
        self.assertEqual(body["reasoning_effort"], "high")
        self.assertEqual(body["max_completion_tokens"], 8192)
        self.assertFalse(body["stream"])
        self.assertEqual(body["response_format"], {"type": "json_object"})
        self.assertFalse(set(body) & {"max_tokens", "temperature", "top_p", "thinking", "enable_thinking", "tools"})
        self.assertIn("Connection check", body["messages"][1]["content"][0]["text"])
        self.assertEqual(self.calls, [])

    def test_single_post_raw_reasoning_usage_and_offline_recovery(self):
        b = self.backend()
        report, code = smoke.run("invoke", self.folder, backend=b)
        self.assertEqual(code, 0)
        self.assertEqual(report["output"], {"status": "ok", "count": 0})
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(self.calls[0][0], "https://api.moonshot.cn/v1/chat/completions")
        self.assertEqual(self.calls[0][3], 900)
        raw = json.loads((self.folder / "api-response.bin").read_bytes())
        self.assertIn("reasoning_content", raw["choices"][0]["message"])
        self.assertEqual(report["usage"]["input_tokens"], 0)
        self.assertEqual(report["raw_usage"]["completion_tokens_details"]["reasoning_tokens"], 3)
        os.environ.pop("MOONSHOT_API_KEY")
        with patch("model_api.http.send", side_effect=AssertionError("network forbidden")):
            recovered, code = smoke.run("recover", self.folder)
        self.assertEqual(code, 0)
        self.assertEqual(recovered["output"], report["output"])
        for path in self.folder.iterdir():
            self.assertNotIn(b"synthetic-kimi-credential", path.read_bytes())
        with self.assertRaises(ApiFailure):
            smoke.run("invoke", self.folder, backend=b)
        self.assertEqual(len(self.calls), 1)

    def test_business_output_and_model_identity_are_checked_by_caller(self):
        invalid = ['{"status":"ok","count":false}', '{"status":"ok","count":1}',
                   '{"status":"ok","count":0,"extra":1}', 'not json',
                   '{"status":"ok","count":2,"count":0}']
        for i, content in enumerate(invalid):
            response = {"model": "kimi-k3", "choices": [{"message": {"content": content}, "finish_reason": "stop"}]}
            report, code = smoke.run("invoke", self.folder / str(i), backend=self.backend(response=response))
            self.assertEqual(code, 2)
            self.assertEqual(report["status"], "failed_validation")
        response["model"] = "different-model"
        response["choices"][0]["message"]["content"] = '{"status":"ok","count":0}'
        report, code = smoke.run("invoke", self.folder / "model", backend=self.backend(response=response))
        self.assertEqual(code, 2)

    def test_provider_rejections_do_not_retry(self):
        for i, (status, error_type, expected) in enumerate([
            (401, "invalid_authentication_error", "paused_account"),
            (403, "permission_denied", "paused_account"),
            (400, "invalid_request_error", "paused_configuration"),
            (429, "rate_limit_error", "paused_service"),
            (500, "server_error", "paused_unknown"),
        ]):
            with self.subTest(status=status):
                report, code = smoke.run("invoke", self.folder / str(i), backend=self.backend(
                    status=status, response={"error": {"type": error_type}}))
                self.assertEqual(code, 2)
                self.assertEqual(report["status"], expected)
        self.assertEqual(len(self.calls), 5)

    def test_empty_and_truncated_are_not_success(self):
        for i, (content, finish, expected) in enumerate([
            ("", "stop", "paused_unknown"), ("{", "length", "paused_truncated")
        ]):
            response = {"model": "kimi-k3", "choices": [{"message": {"content": content}, "finish_reason": finish}]}
            report, code = smoke.run("invoke", self.folder / str(i), backend=self.backend(response=response))
            self.assertEqual(code, 2)
            self.assertEqual(report["status"], expected)
            self.assertTrue((self.folder / str(i) / "api-response.bin").exists())

    def test_timeout_reserves_attempt_without_retry(self):
        sender = unittest.mock.Mock(side_effect=TimeoutError())
        b = Backend(self.profile, sender=sender)
        report, code = smoke.run("invoke", self.folder, backend=b)
        self.assertEqual(code, 2)
        self.assertEqual(report["status"], "paused_unknown")
        self.assertIsNone(b.recover(self.request, self.folder))
        with self.assertRaises(ApiFailure):
            b.invoke(self.request, self.folder)
        self.assertEqual(sender.call_count, 1)

    def test_capacity_rejected_before_http_and_no_truncation(self):
        b = self.backend()
        request = copy.deepcopy(self.request)
        request["payload"]["text"] = "长" * 9000
        with self.assertRaises(ApiFailure) as error:
            b.invoke(request, self.folder)
        self.assertEqual(error.exception.status, "paused_capacity")
        self.assertEqual(self.calls, [])
        self.assertFalse(self.folder.exists())

    def test_missing_usage_is_unknown_and_identity_changes_fail_recovery(self):
        response = {"model": "kimi-k3", "choices": [{"message": {"content": '{"status":"ok","count":0}'}, "finish_reason": "stop"}]}
        b = self.backend(response=response)
        result = b.invoke(self.request, self.folder)
        self.assertIsNone(result.usage["input_tokens"])
        self.assertIsNone(result.raw_usage)
        changed = copy.deepcopy(self.request)
        changed["stage"] = "changed"
        with self.assertRaises(ValueError):
            b.recover(changed, self.folder)
        profile = self.profile.describe()
        profile["generation"]["reasoning_effort"] = "low"
        with self.assertRaises(ValueError):
            Backend(profile).recover(self.request, self.folder)
        (self.folder / "api-response.bin").write_bytes(b"{}")
        with self.assertRaises(ValueError):
            b.recover(self.request, self.folder)


if __name__ == "__main__":
    unittest.main()

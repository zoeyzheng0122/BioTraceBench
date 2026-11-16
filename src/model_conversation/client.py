"""model-conversation-1: native messages and tools, immutable physical calls.

Reuses the standalone SDK's transport and secret sanitization. model-api-1 stays
unchanged. Recovery never reads a key or opens a network connection.
"""
import os
import copy
import time
from http.client import HTTPException
from pathlib import Path

from model_api.http import send
from model_api.backend import redact_json, safe_response
from .archive import Stop, digest, encoded, read, seal, verify, write
from .adapters import Adapter

VERSION = "model-conversation-1"
ENDPOINT = "https://api.moonshot.cn/v1/chat/completions"
ESTIMATE = "https://api.moonshot.cn/v1/tokenizers/estimate-token-count"


class Conversation:
    def __init__(self, config, sender=None):
        self.config = copy.deepcopy(config)
        self.adapter = Adapter(config)
        self.profile = self.adapter.c
        self.sender = sender or send

    @property
    def key_env(self):
        return self.profile["key_env"]

    def describe(self):
        return {"protocol": VERSION, "config": self.config, "resolved_profile": self.profile,
                "config_hash": digest(self.config)}

    def preflight(self, messages, tools):
        if "api_limits" in self.config:
            from .input_limits import enforce
            enforce(messages, self.config)
        body = self.adapter.build(messages, tools)
        if len(encoded(body)) > self.config["max_request_bytes"]:
            raise Stop("paused_capacity", "Complete serialized request exceeds byte limit; no truncation")
        if self.config.get("api_limits"):
            from .input_limits import check
            failures = check({"images": []}, self.config["api_limits"], request_bytes=len(encoded(body)))
            if failures:
                raise Stop("paused_capacity", "Deployment request byte limit exceeded")
        return body

    def _call(self, endpoint, body, folder, kind):
        folder = Path(folder)
        if folder.exists():
            raise Stop("attempt_reserved", "Existing attempt must be recovered; never automatically resubmit")
        key = os.environ.get(self.key_env)
        if not key or any(ord(c) < 32 for c in key):
            raise Stop("paused_account", self.key_env + " is absent or invalid")
        if redact_json(body, key) != body or redact_json(self.config, key) != self.config:
            raise Stop("blocked_secret", "Credential found in request content")
        folder.mkdir(parents=True, exist_ok=False)
        write(folder / "request.json", {"protocol": VERSION, "kind": kind, "endpoint": endpoint,
                                       "config": self.config, "body": body, "identity": digest(body)})
        started = time.monotonic()
        allowed = {"content-type", "x-request-id", "request-id", "retry-after", "x-ratelimit-remaining-requests"}
        try:
            sender = self.sender
            if kind == "completion" and self.config.get("stream") and self.sender is send:
                from .streaming import send as stream_send
                sender = stream_send
            status, headers, raw = sender(endpoint, encoded(body),
                self.adapter.headers(key), self.config["timeout"])
        except (OSError, HTTPException, TimeoutError) as exc:
            if hasattr(exc, "raw"):
                (folder / "partial-stream.bin").write_bytes(safe_response(exc.raw, key))
            if getattr(exc, "status", None) is not None:
                partial = getattr(exc, "raw", b"")
                write(folder / "http.json", {"status": exc.status,
                    "elapsed_seconds": time.monotonic() - started,
                    "headers": {k.lower(): str(v).replace(key, "[REDACTED]")
                                for k, v in (getattr(exc, "headers", None) or {}).items() if k.lower() in allowed},
                    "credential_echo_redacted": partial != safe_response(partial, key),
                    "response_complete": False})
            write(folder / "failure.json", {"status": "paused_unknown", "execution": "unknown", "consumption": "unknown"})
            seal(folder)
            raise Stop("paused_unknown", "Connection interrupted; execution and consumption unknown") from None
        safe = safe_response(raw, key)
        (folder / "response.bin").write_bytes(safe)
        write(folder / "http.json", {"status": status, "elapsed_seconds": time.monotonic() - started,
            "headers": {k.lower(): str(v).replace(key, "[REDACTED]") for k, v in headers.items() if k.lower() in allowed},
            "credential_echo_redacted": raw != safe})
        seal(folder)
        return self._recover(body, folder, kind)

    def _recover(self, body, folder, kind):
        folder = Path(folder)
        if not folder.exists():
            return None
        if not (folder / "receipt.json").exists():
            raise Stop("paused_unknown", "Incomplete attempt archive; automatic resubmission forbidden")
        verify(folder)
        saved = read(folder / "request.json")
        expected_endpoint = self.profile["endpoint"] if kind == "completion" else self.profile["estimator"].get("endpoint")
        if kind == "completion" and self.config.get("stream") and self.adapter.protocol == "gemini":
            expected_endpoint = expected_endpoint.removesuffix(":generateContent") + ":streamGenerateContent?alt=sse"
        if kind == "estimate" and self.profile["estimator"]["kind"] == "native_count":
            suffix = {"responses": "/input_tokens", "anthropic": "/count_tokens", "gemini": ":countTokens"}[self.adapter.protocol]
            expected_endpoint = self.profile["endpoint"].removesuffix(":generateContent") + suffix
        if saved.get("endpoint") != expected_endpoint or saved["config"] != self.config or saved["identity"] != digest(body) or saved["body"] != body or saved["kind"] != kind:
            raise Stop("tampered", "Request/configuration identity changed")
        if (folder / "failure.json").exists():
            raise Stop("paused_unknown", "Prior attempt has unknown execution/consumption")
        meta = read(folder / "http.json")
        code = meta["status"]
        if code != 200:
            status = "paused_account" if code in {401, 402, 403} else "paused_rate_limit" if code == 429 else "paused_configuration" if code in {400, 404, 413, 422} else "paused_unknown"
            raise Stop(status, "HTTP " + str(code) + "; archived, not retried")
        try:
            if kind == "completion" and self.config.get("stream"):
                from .streaming import decode
                value = decode((folder / "response.bin").read_bytes(), self.adapter.protocol)
            else:
                value = read(folder / "response.bin")
        except (ValueError, UnicodeError):
            raise Stop("failed_response", "Invalid JSON response archived") from None
        if kind == "estimate":
            if not isinstance(value, dict):
                raise Stop("failed_estimate", "Invalid estimator response")
            if self.profile["estimator"]["kind"] == "native_count":
                total = value.get("totalTokens" if self.adapter.protocol == "gemini" else "input_tokens")
            else:
                total = value.get("data", {}).get("total_tokens")
            if type(total) is not int or total < 0:
                raise Stop("failed_estimate", "Estimator did not return total_tokens")
            return {"total_tokens": total, "raw": value}
        if not isinstance(value, dict):
            raise Stop("failed_response", "Response must be a JSON object")
        result = self.adapter.parse(value)
        result["http"] = meta
        return result

    def invoke(self, messages, tools, attempt_dir):
        if self.profile["estimator"]["kind"] == "offline_only":
            raise Stop("blocked_estimator", "Configure a verified token counter before paid execution")
        for message in messages:
            for part in message.get("content", []) if isinstance(message.get("content"), list) else []:
                expiry = self.profile.get("file_expiries", {}).get(part.get("file_id"))
                persistent = self.profile.get("file_metadata", {}).get(part.get("file_id"), {}).get("expiry_policy") == "provider_persistent"
                if part.get("type") == "file" and not persistent and (expiry is None or expiry <= time.time()):
                    raise Stop("paused_files", "Frozen image file expired; no automatic re-upload")
        endpoint = self.profile["endpoint"]
        if self.config.get("stream") and self.adapter.protocol == "gemini":
            endpoint = endpoint.removesuffix(":generateContent") + ":streamGenerateContent?alt=sse"
        return self._call(endpoint, self.preflight(messages, tools), attempt_dir, "completion")

    def recover(self, messages, tools, attempt_dir):
        return self._recover(self.preflight(messages, tools), attempt_dir, "completion")

    def estimate(self, messages, tools, folder, *, offline=False):
        request_body = self.preflight(messages, tools)
        policy = self.profile["estimator"]
        if policy["kind"] == "offline_only":
            raise Stop("blocked_estimator", "Offline inspection profile has no verified token counter")
        if policy["kind"] == "local_tokenizer":
            from .token_count import estimate
            return estimate(request_body, policy, folder, offline=offline)
        if policy["kind"] == "native_count":
            endpoint, body, _ = self.adapter.count_request(messages, tools)
            if Path(folder).exists():
                result = self._recover(body, folder, "estimate")
            elif offline:
                raise Stop("offline_missing", "No archived native token count")
            else:
                result = self._call(endpoint, body, folder, "estimate")
            result["reserved_input_tokens"] = result["total_tokens"] + policy["reserve_tokens"]
            result["kind"] = "provider_estimate_with_reserve"
            return result
        if policy["kind"] == "fixed_upper_bound":
            # A declared bound is never presented as a measured token count.
            body = {"request_identity": digest(self.preflight(messages, tools)), "policy": policy}
            folder = Path(folder)
            result = {"total_tokens": None, "reserved_input_tokens": policy["input_tokens"],
                      "kind": "declared_upper_bound", "basis": policy["basis"]}
            if folder.exists():
                verify(folder)
                if read(folder / "request.json") != body or read(folder / "result.json") != result:
                    raise Stop("tampered", "Local token reservation changed")
            elif offline:
                raise Stop("offline_missing", "No archived token reservation")
            else:
                folder.mkdir(parents=True)
                write(folder / "request.json", body)
                write(folder / "result.json", result)
                seal(folder)
            return result
        # Estimate actual message/image/history payload. Add exact tool definitions as
        # estimator-only text because the documented estimator has no tools field.
        # Also reserve their UTF-8 byte count, a deliberately conservative extra bound.
        estimate_messages = list(messages)
        if tools:
            estimate_messages.append({"role": "user", "content": encoded(tools).decode()})
        schema_bytes = 0
        if self.profile.get("output_schema"):
            schema_text = encoded(request_body["response_format"])
            schema_bytes = len(schema_text)
            estimate_messages.append({"role": "user", "content": schema_text.decode()})
        body = {"model": self.config["model"], "messages": estimate_messages}
        if Path(folder).exists():
            result = self._recover(body, folder, "estimate")
        elif offline:
            raise Stop("offline_missing", "No archived token estimate")
        else:
            result = self._call(policy["endpoint"], body, folder, "estimate")
        result["reserved_input_tokens"] = result["total_tokens"] + len(encoded(tools)) + schema_bytes
        if schema_bytes:
            result["output_schema_byte_reserve"] = schema_bytes
        return result

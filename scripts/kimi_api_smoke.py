#!/usr/bin/env python3
"""Synthetic K3 acceptance only: one submission, no retries or task execution."""
import argparse
from datetime import datetime
import getpass
import json
import os
from pathlib import Path
import sys
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from model_api import ApiFailure, Backend, implementation_identity
from model_api._json import loads

PROFILE = ROOT / "configs/models/profiles/kimi-k3-text.json"
REQUEST = ROOT / "tests/fixtures/kimi-api-smoke.json"


def validate_result(result):
    """Acceptance belongs to this caller, not to the transport SDK."""
    if result is None:
        raise ApiFailure("no complete archived response", "paused_unknown")
    if result.actual_model != "kimi-k3":
        raise ApiFailure("returned model does not match kimi-k3", "failed_validation")
    try:
        value = loads(result.text)
    except (ValueError, RecursionError):
        raise ApiFailure("final content is not a JSON object", "failed_validation") from None
    if (not isinstance(value, dict) or set(value) != {"status", "count"}
            or value["status"] != "ok" or type(value["count"]) is not int
            or value["count"] != 0):
        raise ApiFailure("final JSON does not match the synthetic expectation", "failed_validation")
    return value


def run(command, attempt_dir=None, *, backend=None):
    backend = backend or Backend(PROFILE)
    request = loads(REQUEST.read_text(encoding="utf-8"))
    backend.preflight(request)
    report = {
        "checked_at": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(),
        "command": command,
        "profile_hash": backend.describe().profile_hash,
        "implementation": implementation_identity(),
        "synthetic_only": True,
        "automatic_retries": 0,
    }
    if command == "preflight":
        return {**report, "status": "offline_preflight_passed", "network_requests": 0}, 0
    folder = Path(attempt_dir)
    # Never replace the original acceptance record, including failed attempts.
    if command == "invoke" and (folder / "smoke-result.json").exists():
        raise ApiFailure("attempt already has an acceptance record; use recover")
    try:
        result = getattr(backend, command)(request, folder)
        report["output"] = validate_result(result)
        if command == "invoke":
            def forbidden(*args, **kwargs):
                raise AssertionError("offline recovery attempted network access")
            key_name = backend.profile.value["key_env"]
            prior_key = os.environ.pop(key_name, None)
            try:
                recovered = Backend(backend.profile, sender=forbidden).recover(request, folder)
                validate_result(recovered)
                if recovered.as_dict() != result.as_dict():
                    raise ApiFailure("offline recovery differs from original", "failed_validation")
            finally:
                if prior_key is not None:
                    os.environ[key_name] = prior_key
        report.update(status="live_verified" if command == "invoke" else "offline_recovery_verified",
                      actual_model=result.actual_model, request_id=result.request_id,
                      finish_reason=result.finish_reason, usage=result.usage,
                      raw_usage=result.raw_usage, elapsed_seconds=result.elapsed_seconds,
                      offline_recovery_verified=True)
        code = 0
    except ApiFailure as exc:
        report.update(status=exc.status, category=exc.category, scope=exc.scope,
                      retryable=exc.retryable, message=str(exc))
        code = 2
    except (ValueError, OSError):
        report.update(status="failed_validation", message="archive or request validation failed")
        code = 2
    if command == "invoke" and folder.is_dir():
        with (folder / "smoke-result.json").open("x", encoding="utf-8") as stream:
            json.dump(report, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.write("\n")
    return report, code


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("preflight", "invoke", "recover"))
    parser.add_argument("--attempt-dir")
    parser.add_argument("--prompt-key", action="store_true",
                        help="Read a key without echo from a terminal, for this process only")
    args = parser.parse_args(argv)
    if args.command != "preflight" and not args.attempt_dir:
        parser.error("--attempt-dir is required for invoke/recover")
    if args.prompt_key and (args.command != "invoke" or not sys.stdin.isatty()):
        parser.error("--prompt-key requires invoke and an interactive terminal")
    prior_key = os.environ.get("MOONSHOT_API_KEY")
    try:
        if args.prompt_key:
            os.environ["MOONSHOT_API_KEY"] = getpass.getpass("MOONSHOT_API_KEY (hidden): ")
        report, code = run(args.command, args.attempt_dir)
    except (ApiFailure, ValueError, OSError):
        report, code = {"status": "failed_validation", "message": "preflight or attempt reservation failed"}, 2
    finally:
        if args.prompt_key:
            if prior_key is None:
                os.environ.pop("MOONSHOT_API_KEY", None)
            else:
                os.environ["MOONSHOT_API_KEY"] = prior_key
    print(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False))
    return code


if __name__ == "__main__":
    raise SystemExit(main())

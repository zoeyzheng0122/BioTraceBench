"""Explicit commands: preparation never implies paid execution."""
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from .common import Stop, digest, read, write


def main(argv=None):
    parser = argparse.ArgumentParser(prog="biotracebench")
    commands = parser.add_subparsers(dest="command", required=True)
    p = commands.add_parser("prepare")
    p.add_argument("--dataset", required=True)
    p.add_argument("--case", action="append", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--office-bin")
    p.add_argument("--selection-manifest")
    p.add_argument("--delivery-policy", choices=["shared-2000px-v1"])
    p.add_argument("--from-prepared", help="Reuse sealed full preparations without reparsing sources")
    p = commands.add_parser("preflight-matrix")
    p.add_argument("--prepared", required=True)
    p.add_argument("--model-set", required=True)
    p.add_argument("--out", required=True)
    p = commands.add_parser("draft")
    p.add_argument("--prepared", required=True)
    p.add_argument("--dataset", help="Dataset root to bind for reproducible task preparation")
    p.add_argument("--template", required=True)
    p.add_argument("--profile", required=True, help="Conversation model profile; resolved into the draft")
    p.add_argument("--out", required=True)
    p = commands.add_parser("freeze")
    p.add_argument("--draft", required=True)
    p.add_argument("--out", required=True)
    for command in ("run", "recover", "launch"):
        p = commands.add_parser(command)
        p.add_argument("--manifest", required=True)
        p.add_argument("--out", required=True)
        if command != "recover":
            p.add_argument("--execute", action="store_true", required=True)
    p = commands.add_parser("extend-limits")
    p.add_argument("--target", action="append", help="Limit extension to CASE/condition; repeat for multiple pairs")
    p.add_argument("--manifest", required=True)
    p.add_argument("--run", required=True)
    for option in ("max-requests", "max-total-tokens", "max-output-tokens", "context-tokens", "max-request-bytes"):
        p.add_argument("--" + option, type=int)
    p = commands.add_parser("export")
    p.add_argument("--run", required=True)
    p.add_argument("--out", required=True)
    p = commands.add_parser("review-retry", help="Prepare a new paired review round from an archived initial answer")
    p.add_argument("--run", required=True)
    p.add_argument("--case", action="append", required=True)
    p.add_argument("--limits", required=True, help="JSON technical-limit increases; output defaults to twice the previous cap")
    p.add_argument("--out", required=True)
    p = commands.add_parser("overview")
    p.add_argument("--run", required=True)
    p.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    if args.command == "prepare":
        from .materials import prepare
        reports = []
        for case in args.case:
            reports.append(prepare(args.dataset, case, Path(args.out)/case, office_bin=args.office_bin,
                                   selection_manifest=args.selection_manifest, delivery_policy=args.delivery_policy,
                                   from_prepared=args.from_prepared))
        write(Path(args.out)/"audit.json", reports)
        print(json.dumps([{k: r[k] for k in ("case_id", "status", "errors")} for r in reports], ensure_ascii=False))
        return int(any(r["status"] != "ready_offline" for r in reports))
    if args.command == "preflight-matrix":
        from .preflight import matrix
        print(json.dumps(matrix(args.prepared, args.model_set, args.out), ensure_ascii=False))
    elif args.command == "draft":
        from .materials import Reader
        draft = read(args.template)
        if draft.get("protocol") == "biotracebench-run-2":
            if not args.dataset:
                raise ValueError("Current drafts require --dataset to reject preparations from an older package")
            from . import dataset_identity
            draft["dataset"] = dataset_identity.dataset(args.dataset)
        if args.profile:
            from model_conversation.profiles import load
            draft["model"] = load(args.profile)
            if draft.get('output_limit_policy') == 'double_within_provider_bounds':
                from .limits import higher_output_limit
                original = draft['model']['max_output_tokens']
                draft['model']['max_output_tokens'] = higher_output_limit(draft['model'])
                draft['output_limit_basis'] = {'baseline': original, 'multiplier': 2,
                    'selected': draft['model']['max_output_tokens'], 'ceiling': draft['model']['api_limits']['provider_max_output_tokens'],
                    'source_kind':'user','source_reference':'Approved plan: twice the configured output baseline within verified bounds.'}
            # A selected model must never inherit another deployment's prices.
            draft["tariff"] = {"currency": None, "version": None, "source_url": None, "retrieved_at": None,
                              "input_accounting": None,
                              "per_million": {k: None for k in ("input", "output", "cache_hit", "cache_write")},
                              "usage_paths": {k: None for k in ("input", "output", "cache_hit", "cache_write")}}
        draft["tasks"], draft["parameter_basis"] = [], []
        for path in sorted(Path(args.prepared).iterdir()):
            if path.is_dir() and (path/"materials.json").exists():
                reader = Reader(path)
                if draft.get("protocol") == "biotracebench-run-2":
                    dataset_identity.verify_prepared(reader, draft["dataset"], live_sources=True)
                draft["tasks"].append({"case_id": reader.manifest["case_id"], "prepared": str(path.resolve()), "required_reads": []})
                draft["parameter_basis"].append({"case_id": reader.manifest["case_id"], "material_identity": reader.identity,
                    "text_characters": sum(m["text_characters"] for m in reader.entries.values()),
                    "image_count": sum(len(m["images"]) for m in reader.entries.values()),
                    "largest_image_bytes": max((image["bytes"] for m in reader.entries.values() for image in m["images"]),default=0),
                    "note": "Measured offline. Output and cumulative token/cost caps still require explicit values and validation."})
        if Path(args.out).exists():
            raise ValueError("Draft output already exists")
        write(args.out, draft)
    elif args.command == "freeze":
        from .runner import freeze
        print(freeze(args.draft, args.out)["identity"])
    elif args.command in {"run", "recover"}:
        from .runner import run
        result = run(args.manifest, args.out, offline=args.command == "recover")
        print(json.dumps(result, ensure_ascii=False))
        return int(result["failure"] is not None)
    elif args.command == "launch":
        from .runner import validate_binding
        validate_binding(read(args.manifest))
        from model_conversation import Conversation
        key_env = Conversation(read(args.manifest)["model"]).key_env
        if not os.environ.get(key_env):
            raise Stop("paused_account", "Inject " + key_env + " into this process before launch")
        output = Path(args.out).resolve()
        output.mkdir(parents=True, exist_ok=True)
        with (output/"worker.stdout.log").open("ab") as stdout, (output/"worker.stderr.log").open("ab") as stderr:
            child = subprocess.Popen([sys.executable, "-B", "-m", "biotracebench.worker", "--manifest", str(Path(args.manifest).resolve()), "--out", str(output), "--execute"],
                                     stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr, start_new_session=True)
        write(output/"worker.json", {"pid": child.pid, "status": "launched_not_completed", "notification": "error.json and one local desktop notification on failure; no polling or chat message delivery"})
        print(json.dumps({"pid": child.pid, "output": str(output)}))
    elif args.command == "extend-limits":
        from .runner import increase_limits
        keys = ("max_requests", "max_total_tokens", "max_output_tokens", "context_tokens", "max_request_bytes")
        changes = {k:getattr(args,k) for k in keys if getattr(args,k) is not None}
        print(json.dumps(increase_limits(args.manifest, args.run, changes, targets=args.target), ensure_ascii=False))
    elif args.command == "review-retry":
        from .review_retry import prepare
        print(json.dumps(prepare(args.run, args.case, read(args.limits), args.out), ensure_ascii=False))
    elif args.command == "export":
        from .export import run_report
        run_report(args.run, args.out)
    elif args.command == "overview":
        from .common import verify_events
        import shutil
        source = Path(args.run)/"management"
        verify_events(source)
        target = Path(args.out)
        target.mkdir(parents=True, exist_ok=False)
        for name in ("overview.json", "overview.csv", "overview.html", "cost-ledger.json", "identity.json"):
            shutil.copyfile(source/name,target/name)
        # Exported links use the original absolute result location.
        page=(target/"overview.html").read_text()
        from html import escape
        page=page.replace('href="../', 'href="'+escape(Path(args.run).resolve().as_uri()+'/',quote=True))
        (target/"overview.html").write_text(page)

    return 0

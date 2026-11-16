"""Offline comparison matrix; never uploads material or calls a provider."""
from collections import Counter
import copy
import sys
from pathlib import Path
from .common import Stop, digest, encoded, read, write, sha, seal
from .materials import Reader
from . import inputs
from model_conversation.profiles import load
from model_conversation.adapters import Adapter
from model_conversation.input_limits import check


def inspect(reader, config):
    entries = list(reader.entries.values())
    images = [{**i, "inline": True, "encoded_bytes": 4 * ((i["bytes"] + 2) // 3)} for e in entries for i in e["images"]]
    stats = {"images": images, "text_bytes": sum(e.get("text_bytes", 0) for e in entries)}
    limits = config.get("api_limits", {})
    failures = check(stats, limits)
    cap = min(config["max_request_bytes"], limits.get("max_request_bytes", config["max_request_bytes"]))
    lower = stats["text_bytes"] + sum(i["encoded_bytes"] for i in images)
    exact_bytes = None
    if lower > cap:
        failures.append({"limit": "max_request_bytes", "actual_lower_bound": lower, "maximum": cap})
    else:
        # Empty image data is a wire-size skeleton only, never a sendable request.
        # All wrappers and source metadata are identical to inputs.messages().
        def skeleton(r, mid, index, delivery):
            return dict(r.entries[mid]["images"][index]), {"type": "image_url", "image_url": {"url": "data:image/png;base64,"}}
        turns = inputs.messages(reader, image_loader=skeleton)
        body = Adapter(config).build(turns, [])
        exact_bytes = len(encoded(body)) + sum(i["encoded_bytes"] for i in images)
        if exact_bytes > cap:
            failures.append({"limit": "max_request_bytes", "actual": exact_bytes, "maximum": cap})
    # Byte counts are not native tokenizer measurements. A large upper screening
    # reserve cannot establish failure; use it only to report a conditional fit.
    image_bound = None
    if config["provider"] == "deepseek":
        image_bound = len(images) * 1024
    elif config["provider"] == "anthropic":
        image_bound = sum(((i["width"]+27)//28)*((i["height"]+27)//28) for i in images)
    text_upper = stats["text_bytes"] + sum((reader.folder / n).stat().st_size for n in ("instruction.md", "schema.json", "dictionary.json"))
    bound = text_upper + image_bound + 16384 if image_bound is not None else None
    native = None
    if failures and config["provider"] in {"deepseek", "openai", "anthropic", "gemini"}:
        native_stats = {"images": [{**i, "inline": False, "encoded_bytes": 0} for i in images]}
        native_failures = check(native_stats, limits)
        native_config = copy.deepcopy(config)
        native_config["file_metadata"], native_config["file_expiries"] = {}, {}
        def file_skeleton(r, mid, index, delivery):
            meta = dict(r.entries[mid]["images"][index])
            identifier = "file-api-preflight-" + meta["sha256"]
            native_config["file_metadata"][identifier] = {**meta, "provider": config["provider"]}
            native_config["file_expiries"][identifier] = 4102444800
            return meta, {"type": "file", "file_id": identifier}
        turns = inputs.messages(reader, image_loader=file_skeleton)
        projected_bytes = len(encoded(Adapter(native_config).build(turns, [])))
        # IDs are placeholders, not receipts. Reserve additional identifier space
        # and check the real serialized request after explicit uploads.
        projected_bytes += len(images) * 256
        native_failures += check({"images": []}, limits, request_bytes=projected_bytes)
        if projected_bytes > config["max_request_bytes"]:
            native_failures.append({"limit": "client_request_bytes", "actual": projected_bytes, "maximum": config["max_request_bytes"]})
        native = {"status": "capacity_exceeded" if native_failures else "candidate_requires_upload_receipts_and_token_verification",
                  "projected_request_bytes": projected_bytes, "identifier_extra_reserve_per_image": 256,
                  "failures": native_failures, "actual_uploads": 0, "kind": "projection_not_api_acceptance"}
    return {"status": "capacity_exceeded" if failures else "requires_token_and_account_verification",
            "failures": failures, "image_count": len(images), "text_bytes": stats["text_bytes"],
            "native_file_delivery": native,
            "request_bytes": exact_bytes, "request_bytes_lower_bound": lower, "client_request_cap": cap,
            "request_size_kind": "exact_serialization" if exact_bytes is not None else "metadata_lower_bound",
            "token_count": {"kind": "unmeasured", "native_tokens": None, "screening_reserve": bound,
                            "meaning": "UTF-8 byte screening with documented image bound and 16384 framing reserve; not a native count or proof of token failure."},
            "review_context": {"kind": "requires_actual_native_history", "output_reserve": config["max_output_tokens"],
                               "gsr_ssr_equal_limits_required": True},
            "unknown_limits": limits.get("unknown", []), "automatic_truncation": False}


def matrix(prepared, model_set, output):
    output = Path(output).resolve()
    if output.exists():
        raise Stop("already_exists", "Preflight reports are immutable; use a new output directory")
    catalog_path = Path(model_set).resolve()
    catalog = read(catalog_path)
    if catalog.get("protocol") != "biotracebench-model-set-1":
        raise ValueError("Expected model-set catalog")
    models = [(m, load(catalog_path.parent / m["profile"])) for m in catalog["models"]]
    if len({m["id"] for m, _ in models}) != len(models):
        raise ValueError("Duplicate model catalog identity")
    rows, cases = [], []
    for path in sorted(Path(prepared).iterdir()):
        if not path.is_dir() or not (path / "materials.json").is_file():
            continue
        reader = Reader(path)
        if not reader.manifest.get("shared_inputs"):
            raise Stop("blocked_materials", "Fair comparison requires shared preparations")
        case = reader.manifest["case_id"]
        evidence = reader.manifest["evidence_identity"]
        cases.append({"case_id": case, "evidence_identity": evidence, "prepared_identity": reader.identity})
        for model, config in models:
            result = inspect(reader, config)
            rows.append({"case_id": case, "model": model["id"], "evidence_identity": evidence,
                         "config_identity": digest(config), **result})
    counts = dict(Counter(r["status"] for r in rows))
    result = {"protocol": "biotracebench-preflight-matrix-1", "model_set_sha256": sha(catalog_path),
              "implementation": {"preflight": sha(__file__), "inputs": sha(inputs.__file__),
                                 "adapters": sha(sys.modules[Adapter.__module__].__file__)},
              "cases": cases, "models": [m["id"] for m, _ in models], "rows": rows,
              "summary": {"case_count": len(cases), "model_count": len(models), "pair_count": len(rows), "statuses": counts},
              "network_calls": 0, "gold_reads": 0, "live_availability_verified": False,
              "formal_budget_selected": False, "all_models_receive_same_evidence": True}
    output.mkdir(parents=True)
    write(output / "matrix.json", result)
    import csv
    with (output / "matrix.csv").open("w", newline="") as stream:
        writer = csv.writer(stream); writer.writerow(["case_id", "model", "status", "evidence_identity", "request_bytes", "image_count", "failures"])
        for r in rows:
            writer.writerow([r[k] for k in ("case_id", "model", "status", "evidence_identity", "request_bytes", "image_count")] + [encoded(r["failures"]).decode()])
    seal(output)
    return result["summary"]

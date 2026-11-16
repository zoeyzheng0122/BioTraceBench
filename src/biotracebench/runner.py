"""Sequential task execution with independent I0 forks and immutable replay."""
import copy
import hashlib
import fcntl
import json
import os
import sys
import tempfile
import importlib.metadata
import ssl
from decimal import Decimal, DecimalException
from pathlib import Path
from .common import Stop, digest, encoded, event, now, read, seal, sha, verify, verify_events, write
from model_conversation import Conversation
from model_conversation.archive import exact_json, read_exact, DuplicateJSONKey
from .cost import budget_cost, upper, validate_tariff
from .materials import Reader
from .limits import effective, extensions, extend_limits
from . import inputs, prompts, conditions, run_management, submission, dataset_identity
from .schema import references, validate
from .output_contract import POLICIES, output_schema

STAGES = conditions.CANONICAL
INITIAL_REVIEW_POLICY = "biotracebench-received-initial-1"


def runtime_identity():
    packages = {}
    for name in ("Pillow", "openpyxl", "pypdfium2", "tokenizers"):
        try:
            packages[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            packages[name] = None
    if packages["pypdfium2"] is not None:
        from .pdf_material import versions
        packages["PDFium"] = versions()["pdfium_version"]
    return {"python": sys.version.split()[0], "openssl": ssl.OPENSSL_VERSION,
            "packages": packages, "executable": sys.executable}


def implementation():
    source = Path(__file__).parent
    import model_api
    import model_conversation
    files = {}
    for root in (source, Path(model_api.__file__).parent, Path(model_conversation.__file__).parent):
        for path in sorted(root.glob("*.py")):
            files[root.name + "/" + path.name] = sha(path)
    return digest(files)


def validate_manifest(manifest, *, frozen=True):
    def money(value, positive=False):
        try:
            number = Decimal(str(value))
            if not number.is_finite() or number < 0 or positive and number <= 0:
                raise ValueError("Finite monetary bounds/rates are required")
            return number
        except DecimalException:
            raise ValueError("Invalid monetary bound/rate") from None
    if manifest.get("protocol") != "biotracebench-run-2":
        raise ValueError("Use the original source version for archived execution protocols")
    stage_names = conditions.stages(manifest)
    if frozen and manifest.get("state") != "frozen":
        raise ValueError("A frozen manifest is required")
    if manifest.get("cost_purpose", "task_generation") not in {"task_generation", "development_pilot", "connection_acceptance"}:
        raise ValueError("Unknown execution cost purpose")
    retired = {"ontology", "ontology_mode", "tools", "handoff", "handoff_case", "review_budget_amendment", "graph_policy", "ir_output_contract"}
    if retired.intersection(manifest):
        raise ValueError("Remove archived execution options; use the current run template")
    if manifest.get("input_mode") != "all_materials":
        raise ValueError("Complete prepared materials are required")
    if manifest.get("pdf_policy") != dataset_identity.PDF_POLICY or manifest.get("concurrency") != 1:
        raise ValueError("Current material selection policy and concurrency=1 are required")
    if not manifest.get("tasks") or len({t['case_id'] for t in manifest['tasks']}) != len(manifest['tasks']):
        raise ValueError("Unique nonempty task list required")
    if any(set(t) & {"upfront_bundle", "terminology_identity"} for t in manifest["tasks"]):
        raise ValueError("Task inputs must use the current preparation contract")
    if manifest.get("capacity_policy", "stop") not in {"stop", "defer_and_continue"}:
        raise ValueError("Unknown capacity policy")
    if manifest.get("submission_protocol", submission.PROTOCOL) != submission.PROTOCOL:
        raise ValueError("The shared database/annotations contract is required")
    if manifest.get("initial_review_policy", INITIAL_REVIEW_POLICY) != INITIAL_REVIEW_POLICY:
        raise ValueError("Normally received initial responses must be retained for review")
    model = manifest["model"]
    for key in ("max_output_tokens", "context_tokens", "max_request_bytes"):
        if type(model.get(key)) is not int or model[key] <= 0:
            raise ValueError("Missing or invalid model bound: " + key)
    if model["max_output_tokens"] >= model["context_tokens"]:
        raise ValueError("Generation reserve must fit context")
    ceiling = model.get('api_limits', {}).get('provider_max_output_tokens')
    if ceiling is not None and (type(ceiling) is not int or model['max_output_tokens'] > ceiling):
        raise ValueError('Output reserve exceeds the declared provider ceiling')
    connection = Conversation(model)
    if frozen and connection.profile["estimator"]["kind"] == "offline_only":
        raise ValueError("Select and verify the deployment token counter before freezing")
    if frozen and model.get("api_limits", {}).get("output_accounting") == "provider_specific_verify_before_formal_run":
        raise ValueError("Verify whether the deployment output cap includes reasoning before freezing")
    if model.get("api_limits", {}).get("output_accounting") == "visible_answer_only_reasoning_separate" and not model.get("billable_output_token_upper"):
        raise ValueError("Declare a documented billable output bound including separately billed reasoning")
    policy = manifest.get("final_output_policy", "json_object")
    if policy not in POLICIES:
        raise ValueError("Unknown final output policy")
    if "output_schema" in model:
        raise ValueError("Task schemas cannot be overridden in the model config")
    if policy == "json_schema_strict" and not connection.profile["capabilities"].get("json_schema"):
        raise ValueError("Strict final output requires explicit native capability")
    if set(manifest.get("budgets", {})) != set(stage_names):
        raise ValueError("Budget condition keys must match the run protocol")
    for stage in stage_names:
        limits = manifest["budgets"][stage]
        for key in ("max_requests", "max_total_tokens"):
            if type(limits.get(key)) is not int or limits[key] < 1:
                raise ValueError("Unspecified stage budget: " + key)
        money(limits.get("max_cost"), positive=True)
        if limits.get("max_request_cost") is not None:
            money(limits["max_request_cost"], positive=True)
    if "gsr" in stage_names and manifest["budgets"]["gsr"] != manifest["budgets"]["ssr"]:
        raise ValueError("GSR and SSR must use the same resource-limit policy")
    money(manifest.get("max_total_cost"), positive=True)
    if manifest.get("cost_policy", "require_exact") not in {"require_exact", "known_totals_upper_bound"}:
        raise ValueError("Unknown cost policy")
    for key in ("currency", "source_url", "retrieved_at", "version"):
        if not manifest["tariff"].get(key):
            raise ValueError("Price metadata required: " + key)
    validate_tariff(manifest["tariff"])
    if not manifest.get("parameter_basis"):
        raise ValueError("Material-derived parameter basis is required")


def freeze(draft_path, target):
    manifest = read(draft_path)
    manifest["state"] = "frozen"
    manifest["submission_protocol"] = manifest.get("submission_protocol", submission.PROTOCOL)
    manifest["initial_review_policy"] = manifest.get("initial_review_policy", INITIAL_REVIEW_POLICY)
    manifest["execution_protocol"] = prompts.EXECUTION_PROTOCOL
    manifest["ssr_output_contract"] = submission.PROTOCOL
    validate_manifest(manifest)
    stage_names = conditions.stages(manifest)
    manifest["implementation"] = implementation()
    manifest["runtime"] = runtime_identity()
    manifest["prompt_hashes"] = {"i0": digest(prompts.INITIAL), "gsr": digest(prompts.GSR),
                               "ssr": digest(prompts.SSR), "execution": digest([prompts.EXECUTION_PROTOCOL, prompts.CONTINUE_OUTPUT])}
    for task in manifest["tasks"]:
        reader = Reader(task["prepared"])
        if reader.manifest["case_id"] != task["case_id"]:
            raise ValueError("Task identity mismatch")
        if any(e["images"] for e in reader.entries.values()) and not Conversation(manifest["model"]).profile["capabilities"]["vision"]:
            raise ValueError("Task contains images but the selected model has no vision capability")
        task["material_identity"] = reader.identity
        if reader.manifest.get("shared_inputs"):
            task["evidence_identity"] = reader.manifest["evidence_identity"]
            task["selection_identity"] = reader.manifest["selection_identity"]
        task["study_id"] = reader.manifest["study_id"]
        origin = dataset_identity.verify_prepared(reader, manifest.get("dataset"), live_sources=True)
        manifest.setdefault("dataset", origin["dataset"])
        task.update(dataset_identity=origin["dataset"]["identity"], source_identity=origin["identity"],
                    effective_input_identity=sha(reader.folder / "effective-inputs.json"))
        config = {**manifest["model"], "execution_mode": "final"}
        if manifest.get("final_output_policy") == "json_schema_strict":
            task["output_schema_hashes"] = {stage: digest(output_schema(read(reader.folder / "schema.json"), stage, submission.PROTOCOL)) for stage in stage_names}
            config["output_schema"] = output_schema(read(reader.folder / "schema.json"), "i0", submission.PROTOCOL)
        try:
            inputs.capacity_precheck(reader, config, manifest.get("input_delivery"))
            Conversation(config).preflight(inputs.messages(reader, delivery=manifest.get("input_delivery")), [])
        except Stop as exc:
            if exc.status != "paused_capacity" or manifest.get("capacity_policy", "stop") != "defer_and_continue":
                raise
            task["capacity_precheck"] = {"status": "deferred_capacity", "reason": str(exc), "check": "offline_request_bytes", "automatically_extended": False}
    manifest["condition_identity"] = conditions.identity(manifest)
    manifest["task_set_identity"] = digest({"tasks": [{k: task.get(k) for k in ("case_id", "study_id", "material_identity", "dataset_identity", "source_identity", "effective_input_identity")} for task in sorted(manifest["tasks"], key=lambda t: t["case_id"])],
        "prompts": manifest["prompt_hashes"], "dataset": manifest["dataset"], "pdf_policy": manifest["pdf_policy"],
        "stages": manifest["stages"], "input_delivery": digest(manifest.get("input_delivery")), "submission_protocol": submission.PROTOCOL,
        "shared_evidence": {t["case_id"]: t.get("evidence_identity") for t in manifest["tasks"]},
        "initial_review_policy": INITIAL_REVIEW_POLICY, "final_output_policy": manifest.get("final_output_policy", "json_object")})
    manifest["management_protocol"] = run_management.PROTOCOL
    manifest.setdefault("cost_purpose", "task_generation")
    manifest["frozen_at"] = now()
    manifest["identity"] = digest(manifest)
    if Path(target).exists():
        raise ValueError("Frozen manifests cannot be overwritten")
    write(target, manifest)
    return manifest


def validate_binding(manifest):
    validate_manifest(manifest)
    base = {k: v for k, v in manifest.items() if k != "identity"}
    if digest(base) != manifest.get("identity") or implementation() != manifest.get("implementation"):
        raise Stop("tampered", "Frozen manifest or implementation changed")
    if runtime_identity() != manifest["runtime"]:
        raise Stop("changed_runtime", "Runtime/dependency identity differs from frozen manifest")


def ledger(folder, manifest):
    rows = []
    if manifest.get('review_retry'):
        from .review_retry import inherited_costs
        rows.extend(inherited_costs(folder, manifest))
    stage_names = conditions.stages(manifest)
    adapter = Conversation(manifest["model"]).adapter
    for path in sorted(Path(folder).glob("*/**/calls/*/completion/request.json")):
        attempt = path.parent
        meta, raw, cost = None, None, None
        if (attempt / "receipt.json").exists():
            verify(attempt)
        if (attempt / "http.json").exists():
            meta = read(attempt / "http.json")
        if (attempt / "response.bin").exists():
            try:
                if manifest["model"].get("stream"):
                    from model_conversation.streaming import decode
                    raw = decode((attempt / "response.bin").read_bytes(), adapter.protocol)
                else:
                    raw = read(attempt / "response.bin")
            except (ValueError, UnicodeError, Stop):
                pass
        usage = adapter.usage(raw) if isinstance(raw, dict) else None
        if isinstance(usage, dict):
            cost = budget_cost(usage, manifest["tariff"], manifest.get("cost_policy", "require_exact"))
            if not (attempt / "receipt.json").exists() or not meta or meta["status"] != 200:
                cost["budget_upper"] = None
        relative = path.relative_to(folder).parts
        rows.append({"case_id": relative[0], "stage": relative[1], "attempt": str(attempt.relative_to(folder)),
                     "request_hash": sha(path), "http": meta, "raw_usage": usage,
                     "cost": cost, "amount": cost.get("amount") if cost else None,
                     "budget_upper": cost.get("budget_upper") if cost else None})
    known = sum(Decimal(r["amount"]) for r in rows if r["amount"] is not None)
    budget_known = sum(Decimal(r["budget_upper"]) for r in rows if r["budget_upper"] is not None)
    unknown_budget = sum(r["budget_upper"] is None for r in rows)
    summaries = {}
    for task in manifest["tasks"]:
        amounts = {}
        for stage in stage_names:
            calls = [r for r in rows if r["case_id"] == task["case_id"] and r["stage"] == stage and not r.get('historical_round')]
            amounts[stage] = str(sum(Decimal(r["amount"]) for r in calls)) if calls and all(r["amount"] is not None for r in calls) else None
        def combined(*stages):
            return str(sum(Decimal(amounts[s]) for s in stages)) if all(amounts[s] is not None for s in stages) else None
        if manifest.get("scope") == "generation":
            summaries[task["case_id"]] = {"generation": amounts["i0"]}
        else:
            summaries[task["case_id"]] = {**amounts, "I0": amounts["i0"], "I0+GSR": combined("i0", "gsr"),
                                          "I0+SSR": combined("i0", "ssr"), "I0+GSR+SSR": combined(*stage_names)}
    return {"calls": rows, "completion_requests": len(rows),
            "new_completion_requests":sum(not r.get('imported') for r in rows),
            "estimator_requests": sum(read(p).get("kind") == "estimate" for p in Path(folder).glob("*/**/calls/*/estimate*/request.json")),
            "local_token_reservations": sum("policy" in read(p) for p in Path(folder).glob("*/**/calls/*/estimate*/request.json")),
            "known_budget_upper": str(budget_known), "unknown_budget_calls": unknown_budget,
            "total_budget_upper": str(budget_known) if not unknown_budget else None,
            "cost_policy": manifest.get("cost_policy", "require_exact"),
            "known_cost": str(known), "unknown_cost_calls": sum(r["amount"] is None for r in rows),
            "total_cost": str(known) if all(r["amount"] is not None for r in rows) else None,
            "currency": manifest["tariff"]["currency"], "basis": "tariff_estimate_not_invoice", "conditions": summaries}


def check_budget(manifest, run_dir, case_id, stage, estimated_input):
    costs = ledger(run_dir, manifest)
    calls = [r for r in costs["calls"] if r["case_id"] == case_id and r["stage"] == stage and not r.get('historical_round')]
    limits = manifest["budgets"][stage]
    if costs["unknown_budget_calls"]:
        raise Stop("paused_unknown_cost", "Prior consumption cannot be priced; refusing further paid calls")
    if len(calls) >= limits["max_requests"]:
        raise Stop("paused_budget", "Physical request limit reached")
    total_tokens = 0
    for row in calls:
        values = row["cost"]["tokens"]
        total_tokens += values["input"] + values["output"]
    output = manifest["model"]["max_output_tokens"]
    maximum_input = manifest["model"].get("api_limits", {}).get("max_input_tokens")
    if maximum_input is not None and estimated_input > maximum_input:
        raise Stop("paused_capacity", "Actual history exceeds the deployment input-token limit")
    if estimated_input + output > manifest["model"]["context_tokens"]:
        raise Stop("paused_capacity", "History plus tools/images/output exceeds declared context")
    billable_output = manifest["model"].get("billable_output_token_upper", output)
    if total_tokens + estimated_input + billable_output > limits["max_total_tokens"]:
        raise Stop("paused_budget", "Stage token budget reached")
    maximum = upper(estimated_input, billable_output, manifest["tariff"])
    request_cap = limits.get("max_request_cost")
    if request_cap is not None and maximum > Decimal(str(request_cap)):
        raise Stop("paused_budget", "Worst-case next request would exceed per-request monetary budget")
    if sum(Decimal(r["budget_upper"]) for r in calls) + maximum > Decimal(str(limits["max_cost"])) or Decimal(costs["known_budget_upper"]) + maximum > Decimal(str(manifest["max_total_cost"])):
        raise Stop("paused_budget", "Worst-case next request would exceed monetary budget")


def check_spent(manifest, run_dir, case_id, stage):
    costs = ledger(run_dir, manifest)
    if costs["unknown_budget_calls"]:
        raise Stop("paused_unknown_cost", "Usage/cost is unknown; original response retained, queue paused")
    calls = [r for r in costs["calls"] if r["case_id"] == case_id and r["stage"] == stage and not r.get('historical_round')]
    limits = manifest["budgets"][stage]
    tokens = sum(r["cost"]["tokens"]["input"]+r["cost"]["tokens"]["output"] for r in calls)
    cost = sum(Decimal(r["budget_upper"]) for r in calls)
    request_cap = limits.get("max_request_cost")
    if request_cap is not None and any(Decimal(r["budget_upper"]) > Decimal(str(request_cap)) for r in calls):
        raise Stop("paused_budget", "Actual request usage exceeded its monetary bound; response retained")
    if tokens > limits["max_total_tokens"] or cost > Decimal(str(limits["max_cost"])) or Decimal(costs["known_budget_upper"]) > Decimal(str(manifest["max_total_cost"])):
        raise Stop("paused_budget", "Actual usage exceeded the frozen bound; response retained")


def phase(manifest, task, stage, reader, run_dir, transport, parent=None, offline=False):
    directory = run_dir / task["case_id"] / stage
    directory.mkdir(parents=True, exist_ok=True)
    verify_events(directory)
    if parent:
        verify(parent)
        snapshot = read_exact(parent / "snapshot.json")
        messages = copy.deepcopy(snapshot["messages"])
        start_hash = digest(messages)
        messages.append({"role": "user", "content": prompts.GSR if stage == "gsr" else prompts.SSR})
    else:
        current_limits = effective(manifest, extensions(manifest, run_dir), task["case_id"], stage)
        inputs.capacity_precheck(reader, current_limits["model"], manifest.get("input_delivery"))
        messages = inputs.messages(reader, delivery=manifest.get("input_delivery"))
        start_hash = None
    branch = {"case_id": task["case_id"], "stage": stage, "i0_history_sha256": start_hash,
              "material_identity": reader.identity, "manifest_identity": manifest["identity"],
              "parent_final_identity": verify(parent) if parent else None,
              "parent_path": str(parent.relative_to(run_dir)) if parent else None}
    if parent:
        branch.update(initial_review_policy=INITIAL_REVIEW_POLICY, initial_submission_status=snapshot["status"],
                      initial_database_schema_valid=snapshot["assessment"]["database_schema_valid"])
    if (directory / "branch.json").exists() and read(directory / "branch.json") != branch:
        raise Stop("tampered", "Branch origin changed")
    write(directory / "branch.json", branch)
    final_parts = []
    limit_entries = extensions(manifest, run_dir)
    current = effective(manifest, limit_entries, task["case_id"], stage)
    for index in range(current["budgets"][stage]["max_requests"]):
        call = directory / "calls" / f"{index:05d}"
        attempt = call / "completion"
        specs = []
        mode = "final"
        turn_limits = effective(manifest, limit_entries, task["case_id"], stage, index)
        turn_config = {**turn_limits["model"], "execution_mode": "continuation" if final_parts else "final"}
        if manifest.get("final_output_policy") == "json_schema_strict" and turn_config["execution_mode"] == "final":
            turn_config["output_schema"] = output_schema(read(reader.folder / "schema.json"), stage, manifest.get("submission_protocol"))
        backend = Conversation(turn_config, sender=transport.sender)
        turn = {"execution_protocol": manifest["execution_protocol"], "mode": mode, "messages_sha256": digest(messages),
                "tools_sha256": digest(specs), "config_sha256": digest(turn_config)}
        turn_path = call / ("turn-" + digest(turn_config) + ".json")
        if turn_path.exists() and read(turn_path) != turn:
            raise Stop("tampered", "Execution phase or native history changed")
        write(turn_path, turn)
        if attempt.exists():
            result = backend.recover(messages, specs, attempt)
        else:
            estimate = backend.estimate(messages, specs, call / ("estimate-" + digest(turn_config)[:16]), offline=offline)
            check_budget(current, run_dir, task["case_id"], stage, estimate["reserved_input_tokens"])
            if offline:
                raise Stop("offline_missing", "No archived response for the next step")
            event(directory, "request_started", index=index, body_sha256=digest(backend.preflight(messages, specs)), estimate=estimate)
            try:
                result = backend.invoke(messages, specs, attempt)
            except (Stop, ValueError, OSError) as exc:
                event(directory, "request_stopped", index=index, status=getattr(exc,"status","failed_local"),
                      execution_or_consumption="consult_archive_unknown_until_confirmed", automatic_retry=False)
                raise
            event(directory, "request_finished", index=index, status=result.get("status"),
                  finish_reason=result.get("finish_reason"), response_archive=str(attempt.relative_to(run_dir)))
        if result["status"] != "ok":
            partial = result["message"]
            can_continue = (result["status"] == "paused_truncated" and mode == "final"
                            and not partial.get("tool_calls") and isinstance(partial.get("content"), str)
                            and current["model"]["max_output_tokens"] > turn_config["max_output_tokens"])
            if can_continue:
                check_spent(current, run_dir, task["case_id"], stage)
                final_parts.append(partial["content"])
                messages.append(copy.deepcopy(partial))
                messages.append({"role":"user", "content":prompts.CONTINUE_OUTPUT})
                event(directory, "continue_truncated_output", call_index=index, response_identity=digest(partial))
                continue
            raise Stop(result["status"], "Model response did not finish normally; response and usage archived")
        check_spent(current, run_dir, task["case_id"], stage)
        message = result["message"]
        messages.append(copy.deepcopy(message))  # retain ALL assistant fields, including reasoning_content
        if message.get("tool_calls"):
            raise Stop("failed_final_protocol", "Unexpected tool call; response archived without execution")
        final_parts.append(message.get("content") or "")
        content = "".join(final_parts)
        diagnostics, structure_errors = [], []
        parsed_json = False
        wire_value = annotation_value = None
        transport_shape = "unreadable"
        try:
            wire_value, extraction = submission.evaluable_json(content)
            encoded(wire_value)
            parsed_json = extraction['strict_json_valid']
            database, annotation_value, transport_shape = submission.extract(wire_value)
            structure_errors = validate(database, read(reader.folder / "schema.json"))
            if not parsed_json:
                structure_errors.insert(0, {"error": "invalid_final_json", "content_extraction": extraction})
            diagnostics += structure_errors
            if isinstance(database, dict) and all(isinstance(v, list) for v in database.values()):
                diagnostics += references(database, read(reader.folder / "dictionary.json"))
        except (ValueError, TypeError) as exc:
            database = None
            parsed_json = False
            structure_errors = [{"error": "duplicate_json_key" if isinstance(exc, DuplicateJSONKey) else "invalid_final_json"}]
            diagnostics = list(structure_errors)
        annotations = submission.annotation_record(annotation_value, database, read(reader.folder / "dictionary.json"), reader,
            case=task["case_id"], stage=stage, transport=transport_shape,
            raw_hash=hashlib.sha256(content.encode("utf-8")).hexdigest(),
            database_hash=hashlib.sha256(encoded(database) + b"\n").hexdigest())
        diagnostics += annotations["diagnostics"]
        delivery_errors = (validate(wire_value, submission.schema(read(reader.folder / "schema.json")))
                           if parsed_json else copy.deepcopy(structure_errors))
        snapshot = {"messages": messages, "database": database, "diagnostics": diagnostics,
                    "read_receipts": {}, "branch": branch, "final_parts": final_parts,
                    "status": "invalid_output" if structure_errors else "completed", "annotations": annotations}
        snapshot["assessment"] = {
            "protocol": "biotracebench-output-assessment-2", "final_response_received": True,
            "json_parseable": parsed_json, "response_classification": "invalid_final_output" if structure_errors else "readable_database",
            "finish_reason": result.get("finish_reason"), "database_schema_valid": (
                isinstance(database, dict) and not validate(database, read(reader.folder / "schema.json"))),
            "delivery_contract_valid": parsed_json and not delivery_errors,
            "delivery_contract_errors": delivery_errors,
            "database_structure_errors": structure_errors, "process_diagnostics": [d for d in diagnostics if d not in structure_errors],
            "scientific_correctness": "not_evaluated", "submission_protocol": submission.PROTOCOL,
            "annotations_received": annotations["received"], "annotation_diagnostics": annotations["diagnostics"],
            "completion_meaning": "Database structure and scientific correctness are separate assessments."}
        if manifest.get("final_output_policy") == "json_schema_strict":
            wire_errors = validate(wire_value, output_schema(read(reader.folder / "schema.json"), stage, submission.PROTOCOL)['schema']) if parsed_json else [{'error': 'invalid_final_json'}]
            snapshot['assessment'].update(native_output_schema_errors=wire_errors, native_output_schema_valid=not wire_errors,
                final_output_policy='json_schema_strict', native_schema_requested_on_final_call='output_schema' in turn_config)
        final = directory / "final"
        if final.exists():
            verify(final)
        else:
            final.mkdir()
            write(final / "database.json", database)
            (final / "raw-answer.txt").write_text(content, encoding="utf-8")
            write(final / "snapshot.json", snapshot)
            write(final / "diagnostics.json", diagnostics)
            write(final / "output-assessment.json", snapshot['assessment'])
            write(final / "annotations.json", annotations)
            write(final / "input-delivery.json", {"material_identity": reader.identity,
                "representation": "Complete prepared text and images supplied in the request", "tools": []})
            seal(final)
        event(directory, "phase_complete", status=snapshot["status"], final_identity=verify(final))
        return snapshot["status"], final
    raise Stop("paused_budget", "Physical request limit reached without a final answer")


def retain_initial_review_start(manifest, task, final):
    """Record eligibility from normal delivery, never from scientific correctness."""
    stamp = verify(final)
    snapshot = read_exact(final / "snapshot.json")
    assessment = snapshot.get("assessment", {})
    if (assessment.get("final_response_received") is not True
            or snapshot.get("status") not in {"completed", "invalid_output"}
            or not snapshot.get("messages") or snapshot["messages"][-1].get("role") != "assistant"):
        raise Stop("failed_initial_submission", "No normally completed initial response to use as a review starting point")
    record = {"protocol": INITIAL_REVIEW_POLICY, "case_id": task["case_id"],
              "manifest_identity": manifest["identity"], "material_identity": task["material_identity"],
              "initial_final_identity": stamp, "raw_answer_sha256": sha(final / "raw-answer.txt"),
              "initial_history_sha256": digest(snapshot["messages"]),
              "initial_status": snapshot["status"], "database_schema_valid": assessment.get("database_schema_valid"),
              "response_received": True, "eligible_for_review": True, "host_repaired": False,
              "extra_model_calls": 0, "scientific_correctness": "not_evaluated",
              "reason": "Use the received response and exact native history for both independent branches, including format defects."}
    path = final.parent / "initial-review-start.json"
    if path.exists():
        if read(path) != record:
            raise Stop("tampered", "Initial review starting point changed")
    else:
        write(path, record)
        event(final.parent, "initial_review_start_retained", decision=record)
    return record


def run(manifest_path, output, *, offline=False, sender=None):
    manifest = read(manifest_path)
    validate_binding(manifest)
    stage_names = conditions.stages(manifest)
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    # Global same-account process lock. Never store a key in a lock name or file.
    account_lock = Path(tempfile.gettempdir()) / ("biotracebench-" + Conversation(manifest["model"]).profile["provider"] + "-" + str(os.getuid()) + ".lock")
    with account_lock.open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise Stop("account_busy", "Another BioTraceBench account worker is running") from None
        saved = output / "manifest.json"
        if saved.exists() and read(saved) != manifest:
            raise Stop("tampered", "Run directory belongs to another manifest")
        write(saved, manifest)
        session, existing_requests = run_management.begin(output, manifest, offline)
        transport = Conversation(manifest["model"], sender=sender)
        statuses = {t["case_id"]: {s: "not_started" for s in stage_names} for t in manifest["tasks"]}
        previous_status = read(output/"status.json") if (output/"status.json").exists() else {}
        for case, values in statuses.items():
            for stage in values:
                values[stage] = previous_status.get("tasks",{}).get(case,{}).get(stage,"not_started")
        def change(case, stage, value, reason=None):
            run_management.transition(output,case,stage,statuses[case][stage],value,reason)
            statuses[case][stage] = value
            view = run_management.refresh(output,manifest,{"tasks":statuses},ledger(output,manifest),session,existing_requests)
            write(output/"status.json",{"tasks":statuses,"stage_details":view["rows"],"updated_at":now()})
        run_management.refresh(output,manifest,{"tasks":statuses},ledger(output,manifest),session,existing_requests)
        deferred = []
        failure = None
        try:
            for task in manifest["tasks"]:
                reader = Reader(task["prepared"], task["material_identity"])
                parent = None
                for stage in stage_names:
                    if stage == 'i0' and manifest.get('review_retry'):
                        from .review_retry import initial_answer
                        final = initial_answer(output, manifest, task['case_id'])
                        status = read_exact(final/'snapshot.json')['status']
                        change(task['case_id'], stage, status)
                        retain_initial_review_start(manifest, task, final)
                        parent = final
                        continue
                    change(task["case_id"],stage,"replaying" if (output/task["case_id"]/stage/"final").exists() else "running")
                    try:
                        status, final = phase(manifest, task, stage, reader, output, transport,
                                              parent=parent, offline=offline)
                    except Stop as exc:
                        if exc.status != "paused_capacity" or manifest.get("capacity_policy", "stop") != "defer_and_continue":
                            raise
                        change(task["case_id"],stage,"paused_capacity",str(exc))
                        for later in stage_names[stage_names.index(stage) + 1:]:
                            change(task["case_id"],later,"deferred_capacity",str(exc))
                        item = {"case_id": task["case_id"], "stage": stage, "status": "paused_capacity",
                                "reason": str(exc), "material_identity": task["material_identity"],
                                "limits": effective(manifest, extensions(manifest, output), task["case_id"], stage)["model"],
                                "action": "retain_for_later_limit_review", "automatic_retry": False,
                                "automatic_limit_increase": False, "content_truncated": False}
                        deferred.append(item)
                        write(output / task["case_id"] / stage / "capacity.json", item)
                        write(output / "deferred-capacity.json", deferred)
                        break
                    change(task["case_id"],stage,status)
                    if conditions.canonical(stage) == "i0":
                        retain_initial_review_start(manifest, task, final)
                        parent = final
        except (Stop, ValueError, OSError) as exc:
            failure = {"status": getattr(exc, "status", "failed_local"), "message": str(exc)}
            for case, task_statuses in statuses.items():
                for stage in task_statuses:
                    if task_statuses[stage] in {"running","replaying"}:
                        change(case,stage,failure["status"],failure["message"])
            write(output / "error.json", failure)
        finally:
            result = {"tasks": statuses, "failure": failure, "updated_at": now(), "offline_replay": offline}
            if manifest.get("capacity_policy", "stop") == "defer_and_continue":
                result.update(deferred=deferred, queue_status="stopped_on_failure" if failure else
                              "finished_with_deferred_tasks" if deferred else "finished")
            write(output / "status.json", result)
            costs = ledger(output, manifest)
            write(output / "costs.json", costs)
            report = run_management.refresh(output,manifest,result,costs,session,existing_requests)
            result["stage_details"] = report["rows"]
            result["management"] = {"protocol":run_management.PROTOCOL,"run_id":report["run_id"],"overview":"management/overview.html"}
            write(output/"status.json",result)
            event(output/"management","session_finished",session_id=session,offline_replay=offline,
                  failure=failure,overview_identity=digest(report),cost_ledger_identity=digest(read(output/"management/cost-ledger.json")))
            if not failure and (output/"error.json").exists():
                # Previous error remains in the append-only management history.
                write(output/"error.json",{"status":"resolved_by_resume","current_failure":None,"session_id":session})
        return result


def increase_limits(manifest_path, output, changes, *, targets=None):
    """Record an explicit increase locally; this command never resumes or calls a model."""
    manifest = read(manifest_path)
    validate_binding(manifest)
    provider = Conversation(manifest["model"]).profile["provider"]
    lock_path = Path(tempfile.gettempdir()) / ("biotracebench-" + provider + "-" + str(os.getuid()) + ".lock")
    with lock_path.open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise Stop("account_busy", "Cannot change limits while the account worker runs") from None
        costs = ledger(output, manifest)
        if costs["unknown_budget_calls"]:
            raise Stop("paused_unknown_cost", "Cannot extend with unknown consumption")
        entry = extend_limits(manifest, output, changes, targets=targets)
        run_management.identity(output,manifest)
        event(Path(output)/"management","limits_extended",extension_identity=entry["identity"],
              changes=changes,reason=entry["reason"],start_indices=entry["start_indices"],extra_model_recheck=False)
        return entry

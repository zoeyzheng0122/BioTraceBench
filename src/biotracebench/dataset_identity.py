"""Task-rule identities only; study materials are selected and sealed separately."""
from pathlib import Path
from .common import Stop, digest, read, sha, within
from .material_selection import PDF_POLICY

PROTOCOL = "biotracebench-dataset-inputs-1"
PREPARATION = "biotracebench-materials-4"


def public_files(root):
    root = Path(root).resolve()
    paths = [root / "schemas" / "field-dictionary.json"]
    paths += [p for name in ("schemas", "tasks/shared") for p in sorted((root/name).glob("*"))
              if p.is_file() and p.suffix.lower() in {".json", ".md"}]
    paths += [root / name for name in ("metadata/release.json", "docs/DATA_FORMAT.md") if (root/name).is_file()]
    return sorted(set(paths))


def hashes(root, paths):
    result = {}
    for path in paths:
        path = within(root, Path(path).relative_to(root))
        if path.suffix.lower() == ".pdf" or "gold_standard" in path.relative_to(root).parts:
            raise Stop("blocked_path", "Task-rule identity accepts no PDF payloads or reference answers")
        result[str(path.relative_to(root))] = sha(path)
    return result


def dataset(root):
    root = Path(root).resolve()
    files = hashes(root, public_files(root))
    return {"protocol": PROTOCOL, "root": str(root), "files": files,
            "identity": digest({"protocol": PROTOCOL, "files": files, "pdf_policy": PDF_POLICY})}


def task_sources(root, case, domain):
    """Resolve declared public inputs; legacy defaults apply only to absent keys."""
    import re
    if domain not in {"basic", "clinical"} or not re.fullmatch(r"[BC]\d{3}", case):
        raise Stop("blocked_identity", "Invalid task identity")
    root = Path(root).resolve()
    folder = within(root, Path("tasks") / domain / case)
    task_path = within(folder, "task.json")
    task = read(task_path)
    if task.get("case_id") != case or task.get("domain") != domain:
        raise Stop("blocked_identity", "Task identity mismatch")
    defaults = {"materials_manifest": root/"materials"/domain/case/"materials.json",
                "schema": root/"schemas"/("basic-three.schema.json" if domain == "basic" else "clinical-four-compact.schema.json"),
                "field_dictionary": root/"schemas/field-dictionary.json",
                "complete_prompt": folder/"complete-prompt.md", "prompt": folder/"prompt.md"}
    paths = {"task": task_path}
    for key, default in defaults.items():
        declared = task.get(key)
        if key in task and (not isinstance(declared, str) or not declared or Path(declared).is_absolute()):
            raise Stop("blocked_path", "Task input must declare a relative path: " + key)
        candidate = folder/declared if key in task else default
        path = within(root, candidate)
        allowed = ([root/"materials"/domain/case, root/"metadata/manifests"/domain] if key == "materials_manifest"
                   else [root/"schemas"] if key in {"schema", "field_dictionary"} else [folder])
        if not any(path.is_relative_to(base) for base in allowed) or path.suffix.lower() == ".pdf":
            raise Stop("blocked_path", "Task input is outside its public scope: " + key)
        if key == "materials_manifest" and path.is_relative_to(root/"metadata") and path.name != case + ".json":
            raise Stop("blocked_identity", "Cross-task manifest is forbidden")
        if key == "prompt" and key not in task and not path.exists():
            continue
        if not path.is_file():
            raise Stop("missing_input", "Declared task input is missing: " + key)
        paths[key] = path
    return task, paths


def capture(root, case, domain):
    root = Path(root).resolve()
    common = dataset(root)
    _, paths = task_sources(root, case, domain)
    files = hashes(root, paths.values())
    value = {"protocol": PROTOCOL, "dataset": common, "case_id": case,
             "domain": domain, "task_files": files, "pdf_policy": PDF_POLICY}
    return {**value, "identity": digest(value)}


def verify_prepared(reader, expected=None, *, live_sources=False):
    """New runs reject stale preparations; archived replay uses frozen copies only."""
    report = reader.manifest
    path = reader.folder/"source-identity.json"
    from .shared_inputs import PROTOCOL as SHARED
    if report.get("protocol") not in {PREPARATION, SHARED} or not path.is_file():
        raise Stop("stale_preparation", "Prepare this dataset again in a new directory; legacy cache cannot be relabelled")
    saved = read(path)
    if saved.get("identity") != digest({k: v for k, v in saved.items() if k != "identity"}):
        raise Stop("tampered", "Prepared source identity changed")
    if report.get("source_identity") != saved["identity"] or report.get("dataset_identity") != saved["dataset"]["identity"]:
        raise Stop("tampered", "Prepared dataset binding changed")
    if expected and any(saved["dataset"][k] != expected[k] for k in ("root", "identity")):
        raise Stop("stale_preparation", "Prepared task belongs to a different dataset root or rule version")
    if live_sources and capture(saved["dataset"]["root"], saved["case_id"], saved["domain"]) != saved:
        raise Stop("stale_preparation", "Task, schema, rules or manifest changed after preparation; prepare a new input bundle")
    return saved

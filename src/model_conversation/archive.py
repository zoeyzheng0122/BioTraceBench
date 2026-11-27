"""Generic deterministic archives and append-only audit records. No task logic or credentials."""
import hashlib
import json
import os
from decimal import Decimal
from datetime import datetime, timezone
from pathlib import Path


class Stop(RuntimeError):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status


def encoded(value):
    def render(item):
        if isinstance(item, Decimal):
            if not item.is_finite():
                raise ValueError("Nonfinite JSON number")
            return str(item)
        if isinstance(item, dict):
            if any(not isinstance(key, str) for key in item):
                raise TypeError("JSON object keys must be strings")
            return "{" + ",".join(json.dumps(k, ensure_ascii=False) + ":" + render(v)
                                   for k, v in sorted(item.items())) + "}"
        if isinstance(item, (list, tuple)):
            return "[" + ",".join(render(v) for v in item) + "]"
        return json.dumps(item, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return render(value).encode()


class DuplicateJSONKey(ValueError):
    pass


def exact_json(text):
    """Scientific submissions retain decimal values and reject ambiguous keys."""
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise DuplicateJSONKey("Duplicate JSON key in submission")
            result[key] = value
        return result
    return json.loads(text, parse_float=Decimal, object_pairs_hook=pairs,
                      parse_constant=lambda x: (_ for _ in ()).throw(ValueError("Nonfinite JSON number")))


def read_exact(path):
    return exact_json(Path(path).read_text(encoding="utf-8"))


def digest(value):
    return hashlib.sha256(encoded(value)).hexdigest()


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for piece in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(piece)
    return h.hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"), parse_constant=lambda x: (_ for _ in ()).throw(ValueError(x)))


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    with temp.open("wb") as stream:
        stream.write(encoded(value) + b"\n")
        stream.flush()
        os.fsync(stream.fileno())
    temp.replace(path)


def now():
    return datetime.now(timezone.utc).isoformat()


def within(root, relative):
    root = Path(root).resolve()
    path = root / relative
    if path.is_symlink() or not path.resolve().is_relative_to(root):
        raise Stop("blocked_path", "Path escapes the task boundary")
    return path.resolve()


def seal(folder, name="receipt.json"):
    folder = Path(folder)
    files = {str(p.relative_to(folder)): sha(p) for p in sorted(folder.rglob("*"))
             if p.is_file() and p.name != name}
    write(folder / name, {"files": files, "sha256": digest(files)})
    return digest(files)


def verify(folder, expected=None, name="receipt.json"):
    folder = Path(folder)
    receipt = read(folder / name)
    if digest(receipt["files"]) != receipt["sha256"] or expected and receipt["sha256"] != expected:
        raise Stop("tampered", "Receipt identity changed")
    actual = {str(p.relative_to(folder)) for p in folder.rglob("*") if p.is_file() and p.name != name}
    if actual != set(receipt["files"]):
        raise Stop("tampered", "Archive file set changed")
    for relative, checksum in receipt["files"].items():
        if sha(within(folder, relative)) != checksum:
            raise Stop("tampered", "Archive content changed: " + relative)
    return receipt["sha256"]


def event(folder, kind, **data):
    path = Path(folder) / "events.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    previous = ""
    if path.exists():
        with path.open() as stream:
            for line in stream:
                previous = json.loads(line)["hash"]
    entry = {"time": now(), "kind": kind, "previous": previous, **data}
    entry["hash"] = digest(entry)
    with path.open("ab") as stream:
        stream.write(encoded(entry) + b"\n")
        stream.flush()
        os.fsync(stream.fileno())
    return entry["hash"]


def verify_events(folder):
    previous = ""
    path = Path(folder) / "events.jsonl"
    if not path.exists():
        return previous
    for line in path.read_text().splitlines():
        entry = json.loads(line)
        checksum = entry.pop("hash")
        if entry["previous"] != previous or digest(entry) != checksum:
            raise Stop("tampered", "Event chain changed")
        previous = checksum
    return previous

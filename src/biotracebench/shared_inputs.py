"""Model-independent, source-bound projections of sealed material preparations."""
import copy
import math
import re
import shutil
from pathlib import Path
from .common import Stop, digest, encoded, read, write, sha, seal, within

PROTOCOL = "biotracebench-shared-inputs-1"
SELECTION = "biotracebench-material-selection-1"
POLICY = {"name": "shared-2000px-v1", "long_edge": 2000, "resample": "LANCZOS",
          "format": "PNG", "mode": "RGB", "compress_level": 9, "enlarge": False,
          "text_truncation": False, "model_specific_selection": False}
CELL_LEGEND = {"representation": "compact-workbook-1", "cell_tuple": ["cell", "raw", "overrides"],
               "defaults": {"cached": "same as raw", "number_format": "General", "is_formula": False},
               "row_runs": "row_range=[first,last] repeats cell_columns tuples at every source row, restoring the row number in each cell address.",
               "meaning": "Exact source cell records. Overrides replace defaults; omitted overrides use defaults."}


def pack_cell(cell):
    value = {k: v for k, v in cell.items() if k not in {"cell", "raw"}}
    for k, default in (("cached", cell["raw"]), ("number_format", "General"), ("is_formula", False)):
        if k in value and encoded(value[k]) == encoded(default):
            del value[k]
    return [cell["cell"], cell["raw"], value]


def unpack_cell(cell):
    address, raw, overrides = cell
    return {"cell": address, "raw": raw, "cached": raw, "number_format": "General",
            "is_formula": False, **overrides}


def expand_record(record):
    """Recover selected source records from one compact row or row run."""
    if "row_range" in record:
        for row in range(record["row_range"][0], record["row_range"][1] + 1):
            yield {"sheet": record["sheet"], "row": row,
                   "cells": [unpack_cell([col + str(row), raw, extra]) for col, raw, extra in record["cell_columns"]]}
    elif "cells" in record:
        yield {**record, "cells": [unpack_cell(c) for c in record["cells"]]}
    elif record.get("representation") != "compact-workbook-1":
        yield record


def compact_workbook(source, target, rule):
    """Stream rows; check exact roundtrip before emitting each retained record."""
    import json
    wanted = set(rule.get("sheets", []))
    seen, kept, omitted = set(), 0, 0
    pending = None
    def pattern(row):
        if set(row) != {"sheet", "row", "cells"}:
            return None
        cells = [[re.sub(r"[0-9]+$", "", c[0]), c[1], c[2]] for c in row["cells"]]
        return {"sheet": row["sheet"], "cell_columns": cells}
    def flush(out, item):
        if item is not None:
            out.write(encoded(item["first"] if item["start"] == item["end"] else {**item["pattern"], "row_range": [item["start"], item["end"]]}).decode() + "\n")
    original_hash, restored_hash = __import__("hashlib").sha256(), __import__("hashlib").sha256()
    with source.open(encoding="utf-8", newline="") as inp, target.open("w", encoding="utf-8", newline="") as out:
        out.write(encoded(CELL_LEGEND).decode() + "\n")
        for line in inp:
            row = json.loads(line)
            if "sheet" in row:
                seen.add(row["sheet"])
                if wanted and row["sheet"] not in wanted:
                    omitted += 1
                    continue
                spans = rule.get("rows", {}).get(row["sheet"])
                if spans and not any(a <= row["row"] <= b for a, b in spans):
                    omitted += 1
                    continue
            if "cells" in row and row.get("sheet") in rule.get("columns", {}):
                selected_columns = set(rule["columns"][row["sheet"]])
                row = {**row, "cells": [c for c in row["cells"] if re.sub(r"[0-9]+$", "", c["cell"]) in selected_columns]}
                if not row["cells"]:
                    continue
            compact = {**row, "cells": [pack_cell(c) for c in row["cells"]]} if "cells" in row else row
            restored = {**compact, "cells": [unpack_cell(c) for c in compact["cells"]]} if "cells" in compact else compact
            if encoded(restored) != encoded(row):
                raise Stop("blocked_materials", "Compact cell roundtrip failed")
            original_hash.update(encoded(row)); restored_hash.update(encoded(restored))
            pat = pattern(compact)
            if pat is not None and pending is not None and pat == pending["pattern"] and row["row"] == pending["end"] + 1:
                pending["end"] = row["row"]
            else:
                flush(out, pending); pending = None
                if pat is not None:
                    pending = {"first": compact, "pattern": pat, "start": row["row"], "end": row["row"]}
                else:
                    out.write(encoded(compact).decode() + "\n")
            kept += 1
        flush(out, pending)
    if wanted - seen:
        raise Stop("blocked_manifest", "Unknown selected worksheet: " + ", ".join(sorted(wanted - seen)))
    return {"representation": "compact-workbook-1", "retained_records": kept, "excluded_records": omitted,
            "retained_records_sha256": original_hash.hexdigest(), "roundtrip_sha256": restored_hash.hexdigest()}


def selection_for(path, reader):
    value = read(path)
    if value.get("protocol") != SELECTION or not isinstance(value.get("cases"), dict):
        raise Stop("blocked_manifest", "Expected shared source-selection manifest")
    case = reader.manifest["case_id"]
    rule = value["cases"].get(case)
    origin = read(reader.folder / "source-identity.json")
    if not rule or rule.get("source_identity") != origin["identity"]:
        raise Stop("blocked_identity", "Selection is not bound to this task and source manifest")
    entries = {e["source"]: e for e in reader.entries.values()}
    decisions = rule.get("files", [])
    if (len(decisions) != len(entries) or {d.get("path") for d in decisions} != set(entries)):
        raise Stop("blocked_manifest", "Every prepared source needs exactly one selection decision")
    for d in decisions:
        if d.get("decision") not in {"keep", "exclude", "select"} or not d.get("reason") or not d.get("basis"):
            raise Stop("blocked_manifest", "Selection needs a decision, reason and source basis")
        e = entries[d["path"]]
        if d.get("sha256") != e["sha256"]:
            raise Stop("blocked_identity", "Selection source checksum changed")
        from .material_selection import main_representation
        if main_representation({**e, "path": e["source"]}) and (d["decision"] != "keep" or set(d) & {"pages", "sheets", "rows", "columns"}):
            raise Stop("blocked_manifest", "The complete main article must be retained")
        if d["decision"] != "select" and set(d) & {"pages", "sheets", "rows", "columns"}:
            raise Stop("blocked_manifest", "Partial selection requires decision=select")
        if d["decision"] == "select":
            if e["format"] == ".pdf":
                pages = d.get("pages")
                if (set(d) & {"sheets", "rows", "columns"} or not isinstance(pages, list) or not pages
                        or any(type(n) is not int for n in pages) or pages != sorted(set(pages))
                        or min(pages) < 1 or max(pages) > e["pdf"]["page_count"]):
                    raise Stop("blocked_manifest", "Selected PDF pages must be ordered, unique and in range")
            elif e["format"] in {".xls", ".xlsx"}:
                if "pages" in d or not isinstance(d.get("sheets"), list) or not d["sheets"] or len(set(d["sheets"])) != len(d["sheets"]):
                    raise Stop("blocked_manifest", "Workbook selection requires unique worksheet names")
                for sheet, columns in d.get("columns", {}).items():
                    if sheet not in d["sheets"] or not columns or any(not isinstance(c, str) or not re.fullmatch(r"[A-Z]{1,3}", c) for c in columns):
                        raise Stop("blocked_manifest", "Invalid selected source columns")
                for sheet, spans in d.get("rows", {}).items():
                    if sheet not in d["sheets"] or not spans or any(not isinstance(x, list) or len(x) != 2 or any(type(n) is not int for n in x) or not 1 <= x[0] <= x[1] for x in spans):
                        raise Stop("blocked_manifest", "Invalid source row ranges")
            else:
                raise Stop("blocked_manifest", "Partial selection supports PDFs and workbooks only")
    return {"protocol": SELECTION, "case_id": case, **rule}


def derive(source, output, selection_manifest, delivery_policy="shared-2000px-v1"):
    from .materials import Reader
    from . import dataset_identity
    from PIL import Image, __version__ as pillow_version
    reader = Reader(source)
    dataset_identity.verify_prepared(reader, live_sources=True)
    if reader.manifest.get("shared_inputs"):
        raise Stop("blocked_manifest", "Derive from an original full preparation, not another projection")
    if delivery_policy != POLICY["name"]:
        raise ValueError("Unknown shared delivery policy")
    selection = selection_for(selection_manifest, reader)
    output = Path(output).resolve()
    dataset_root = Path(read(reader.folder / "source-identity.json")["dataset"]["root"]).resolve()
    if output.exists() or output.is_relative_to(reader.folder) or output.is_relative_to(dataset_root):
        raise Stop("blocked_path", "Use a new external shared preparation directory")
    output.mkdir(parents=True)
    for name in ("instruction.md", "schema.json", "dictionary.json", "task.json", "source-identity.json"):
        shutil.copyfile(reader.folder / name, output / name)
    report = copy.deepcopy(reader.manifest)
    report.update(protocol=PROTOCOL, materials=[], excluded=report["excluded"][:], shared_inputs=True,
                  parent_preparation_identity=reader.identity, delivery_policy=POLICY,
                  selection_identity=digest(selection), pillow_version=pillow_version)
    decisions = {d["path"]: d for d in selection["files"]}
    for mid, entry in reader.entries.items():
        rule = decisions[entry["source"]]
        if rule["decision"] == "exclude":
            report["excluded"].append(copy.deepcopy(rule)); continue
        old, folder = reader.folder / mid, output / mid
        folder.mkdir()
        new = copy.deepcopy(entry)
        pages = rule.get("pages") if entry["format"] == ".pdf" else None
        image_indices = [p["image_index"] for p in entry["pdf"]["pages"] if pages is None or p["page"] in pages] if entry["format"] == ".pdf" else list(range(len(entry["images"])))
        new["images"] = []
        for index in image_indices:
            meta = entry["images"][index]
            path = within(old, meta["path"])
            with Image.open(path) as im:
                picture = im.convert("RGB")
                factor = min(1, POLICY["long_edge"] / max(picture.size))
                size = tuple(max(1, math.floor(n * factor)) for n in picture.size)
                if size != picture.size:
                    resized = picture.resize(size, Image.Resampling.LANCZOS); picture.close(); picture = resized
                target = folder / f"image-{len(new['images']):05d}.png"
                picture.save(target, format="PNG", compress_level=9); picture.close()
            new["images"].append({**meta, "path": target.name, "sha256": sha(target),
                "width": size[0], "height": size[1], "bytes": target.stat().st_size,
                "prepared_sha256": meta["sha256"], "original_dimensions": [meta["width"], meta["height"]]})
        text = old / "content.txt"
        if entry["format"] == ".pdf":
            with text.open(encoding="utf-8", newline="") as stream:
                content = stream.read()
            new_pages, offset = [], 0
            with (folder / "content.txt").open("w", encoding="utf-8", newline="") as out:
                for page in entry["pdf"]["pages"]:
                    if pages is not None and page["page"] not in pages:
                        continue
                    value = content[page["text_start"]:page["text_end"]]
                    marker = f"\n=== PDF page {page['page']} ===\n"
                    out.write(marker + value)
                    start = offset + len(marker); offset = start + len(value)
                    new_pages.append({**page, "image_index": len(new_pages), "source_text_start": page["text_start"],
                                      "source_text_end": page["text_end"], "text_start": start, "text_end": offset})
            new["pdf"].update(pages=new_pages, page_count=len(new_pages), original_page_count=entry["pdf"]["page_count"])
        elif entry["format"] in {".xls", ".xlsx"}:
            new["projection"] = compact_workbook(text, folder / "content.txt", rule)
        elif text.exists():
            shutil.copyfile(text, folder / "content.txt")
        if (folder / "content.txt").exists():
            target = folder / "content.txt"
            with target.open(encoding="utf-8", newline="") as stream:
                new["text_characters"] = sum(len(s) for s in iter(lambda: stream.read(65536), ""))
            new["text_bytes"] = target.stat().st_size
            new["content_sha256"] = sha(target)
        report["materials"].append(new)
    write(output / "source-selection.json", selection)
    write(output / "delivery-policy.json", POLICY)
    evidence = {"protocol": PROTOCOL, "case_id": report["case_id"], "source_identity": report["source_identity"],
                "selection_identity": report["selection_identity"], "policy": POLICY,
                "materials": [{"source": e["source"], "content_sha256": e.get("content_sha256"),
                               "images": [i["sha256"] for i in e["images"]]} for e in report["materials"]]}
    report["evidence_identity"] = digest(evidence)
    write(output / "evidence.json", {**evidence, "identity": report["evidence_identity"]})
    effective = {"protocol": PROTOCOL, "case_id": report["case_id"], "included": report["materials"],
                 "excluded": report["excluded"], "evidence_identity": report["evidence_identity"],
                 "source_identity": report["source_identity"], "evidence_coverage": "task_scoped_source_review",
                 "scientific_sufficiency": "not_established_by_software_checks"}
    write(output / "effective-inputs.json", effective)
    write(output / "materials.json", report)
    seal(output)
    return report


def prepare(dataset, case_id, output, *, selection_manifest, delivery_policy, from_prepared=None, office_bin=None):
    if not re.fullmatch(r"[BC][0-9]{3}", case_id):
        raise ValueError("Expected Bnnn or Cnnn task ID")
    if from_prepared:
        source = Path(from_prepared) / case_id
        origin = read(source / "source-identity.json")
        if origin["case_id"] != case_id or Path(origin["dataset"]["root"]).resolve() != Path(dataset).resolve():
            raise Stop("blocked_identity", "Full preparation and requested dataset/case disagree")
        return derive(source, output, selection_manifest, delivery_policy)
    from .materials import prepare as full_prepare
    source = Path(output).resolve().parent / "_full" / case_id
    result = full_prepare(dataset, case_id, source, office_bin=office_bin)
    if result["status"] != "ready_offline":
        raise Stop("blocked_materials", "Full preparation failed before shared projection")
    return derive(source, output, selection_manifest, delivery_policy)



def validate(reader):
    """Receipts cover every derived byte; additionally validate semantic bindings."""
    report = reader.manifest
    selection = read(reader.folder / "source-selection.json")
    evidence = read(reader.folder / "evidence.json")
    if (digest(selection) != report["selection_identity"] or read(reader.folder / "delivery-policy.json") != POLICY
            or evidence["identity"] != digest({k: v for k, v in evidence.items() if k != "identity"})
            or evidence["identity"] != report["evidence_identity"]):
        raise Stop("tampered", "Shared input selection or evidence identity changed")
    for e in reader.entries.values():
        if e.get("content_sha256") and sha(reader.folder / e["id"] / "content.txt") != e["content_sha256"]:
            raise Stop("tampered", "Shared text changed")
        if any(max(i["width"], i["height"]) > 2000 for i in e["images"]):
            raise Stop("blocked_materials", "Shared image policy violated")
        if e["format"] == ".pdf":
            pages = e["pdf"]["pages"]
            if len(pages) != e["pdf"]["page_count"] or len(pages) != len(e["images"]):
                raise Stop("blocked_materials", "Shared PDF page/image coverage changed")
            previous = 0
            for index, page in enumerate(pages):
                if page["image_index"] != index or not previous < page["page"] <= e["pdf"]["original_page_count"]:
                    raise Stop("blocked_materials", "Invalid original PDF page locator")
                previous = page["page"]

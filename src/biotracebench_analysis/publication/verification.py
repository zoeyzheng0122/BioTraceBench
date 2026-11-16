"""Validate a sealed BioTraceBench materials package without model or network calls."""
from collections import Counter
from pathlib import Path
from urllib.parse import unquote
from zipfile import BadZipFile, ZipFile
import argparse
import gzip
import hashlib
import json
import re

MANIFEST = "04_Reproducibility/06_Verification/release-manifest.json"
NAVIGATION = (
    "index.html", "README.md", "01_Manuscript/README.md",
    "04_Reproducibility/README.md", "05_Archive/README.md",
    "03_Benchmark_Data/README.md",
    "03_Benchmark_Data/01_Task_Materials/task_index.html",
    "04_Reproducibility/04_Human_Review/README.md",
    "02_Figures/03_Plotting_Code/README.md",
)

def require(condition, message):
    if not condition:
        raise ValueError(message)

def read(path):
    path = Path(path)
    data = path.read_bytes()
    return json.loads(gzip.decompress(data) if path.suffix == ".gz" else data)

def digest(path):
    result = hashlib.sha256()
    with Path(path).open("rb") as source:
        for block in iter(lambda: source.read(4194304), b""):
            result.update(block)
    return result.hexdigest()

def local_path(root, relative):
    require(isinstance(relative, str) and relative, "Empty material path")
    raw = Path(relative)
    require(not raw.is_absolute() and ".." not in raw.parts, "Invalid material path: " + relative)
    path = root / raw
    require(path.resolve().is_relative_to(root), "Material path leaves package: " + relative)
    return path

def verify_file_manifest(root, manifest):
    """Every explicitly listed file is mandatory; filenames imply no exemptions."""
    require(isinstance(manifest.get("files"), list), "Missing release file inventory")
    seen = set()
    for item in manifest["files"]:
        name = item["path"]
        require(name not in seen, "Duplicate manifest entry: " + name)
        seen.add(name)
        path = local_path(root, name)
        require(path.is_file() and not path.is_symlink(), "Required file missing: " + name)
        require(path.stat().st_size == item["size"], "File size differs: " + name)
        require(digest(path) == item["sha256"], "File hash differs: " + name)
    return len(seen)

def verify_checksum_anchor(root):
    """The top-level checksum anchors the release inventory itself."""
    checks = {}
    for line in (root / "SHA256SUMS").read_text().splitlines():
        if not line.strip():
            continue
        fields = line.split(maxsplit=1)
        require(len(fields) == 2 and re.fullmatch(r"[0-9a-f]{64}", fields[0]), "Invalid checksum line")
        name = fields[1].lstrip("*")
        require(name not in checks, "Duplicate checksum entry: " + name)
        checks[name] = fields[0]
        require(digest(local_path(root, name)) == fields[0], "Checksum anchor differs: " + name)
    require(MANIFEST in checks, "Release inventory is not anchored by SHA256SUMS")

def check_database(database, inventory):
    require(isinstance(database, dict), "Parsed database must be an object")
    if isinstance(database.get("database"), dict):
        database = database["database"]
    rows = {row["id"]: row for row in inventory["rows"]}
    expected = {(row["table"], row["row_index"]): set()
                for row in rows.values() if row["side"] == "prediction"}
    cells = []
    for cell in inventory["cells"]:
        if cell["side"] == "prediction" and cell.get("present", True):
            row = rows[cell["row"]]
            key = row["table"], row["row_index"]
            expected[key].add(cell["field"])
            cells.append((*key, cell["field"], json.loads(cell["value_json"])))
    actual = {(table, index): set(row) for table, data in database.items()
              if isinstance(data, list) for index, row in enumerate(data) if isinstance(row, dict)}
    require(actual == expected, "Database records or field sets differ from scoring inventory")
    for table, index, field, value in cells:
        require(database[table][index][field] == value,
                "Database value differs from scoring inventory: " + table + "." + field)
    return len(cells)

def verify_navigation(root):
    count = 0
    for name in NAVIGATION:
        path = root / name
        content = path.read_text()
        links = (re.findall(r"""href=["']([^"']+)""", content) if path.suffix == ".html"
                 else re.findall(r"\]\(([^)]+)\)", content))
        for link in links:
            if "://" in link or link.startswith("#"):
                continue
            target = (path.parent / unquote(link.split("#")[0])).resolve()
            require(target.is_relative_to(root) and target.exists(),
                    "Broken material link: " + name + " -> " + link)
            count += 1
    return count

def verify_materials(artifact_root):
    root = Path(artifact_root).resolve()
    require(root.is_dir(), "Materials directory does not exist")
    repro = root / "04_Reproducibility"
    manifest = read(root / MANIFEST)
    verify_checksum_anchor(root)
    file_count = verify_file_manifest(root, manifest)
    binding = read(repro / "06_Verification/version_binding.json")
    release = read(root / "release_manifest.json")
    stage = binding["stage"]
    require(manifest["stages"] == release["stages"] == [stage], "Publication stage binding differs")
    status = read(root / release["output_status"])
    positions = status["positions"]
    require(len(positions) == binding["positions"] == release["positions_per_stage"],
            "Model-output position coverage differs")
    require(Counter(item["status"] for item in positions) == Counter(release["raw_outputs"]),
            "Model-output status coverage differs")
    identities = [(item["model"], item["case"], item["stage"]) for item in positions]
    require(len(set(identities)) == len(identities), "Duplicate model-output position")
    require(all(item[2] == stage for item in identities), "Unexpected stage in model-output inventory")
    models = {item[0] for item in identities}
    cases = {item[1] for item in identities}
    require(len(models) == binding["models"] and len(cases) == binding["tasks"],
            "Task or model coverage differs")
    require(len(positions) == len(models) * len(cases), "Incomplete task-by-model grid")
    cells = 0
    for item in positions:
        if item["status"] == "terminal_zero":
            continue
        folder = root / "03_Benchmark_Data/02_Model_Outputs" / item["model"] / item["case"]
        require((folder / "raw-answer.txt").is_file(), "Original answer text is missing")
        packet = read(repro / "02_Published_Evaluation/projection/judgments"
                      / item["model"] / stage / (item["case"] + ".json.gz"))
        if item["status"] == "parseable_database":
            cells += check_database(read(folder / "database.json"), packet["inventory"])
        else:
            require(read(folder / "database.json") is None, "Partial raw text has an invented database")
    materials = root / release["task_materials"]
    sources = read(materials / "metadata/sources.json")["files"]
    for item in sources:
        require(digest(local_path(materials, item["path"])) == item["sha256"],
                "Scientific source hash differs: " + item["path"])
    references = list((repro / "02_Published_Evaluation/projection/references").glob("*.json"))
    require(len(references) == binding["tasks"] and {path.stem for path in references} == cases,
            "Reference task coverage differs")
    for path in references:
        domain = "basic" if path.stem.startswith("B") else "clinical"
        target = materials / "gold_standard" / domain / path.stem / path.name
        require(digest(path) == digest(target), "Reference versions differ: " + path.stem)
        require((materials / "tasks" / domain / path.stem / "task.json").is_file(),
                "Task specification is missing: " + path.stem)
    review = repro / "04_Human_Review"
    sample = read(review / "01_Analysis/analysis_parameters.json")["outputs"]
    for name in ("reviewer_A.json", "reviewer_B.json"):
        require(len(read(review / name)["answers"]) == sample, "Human-review sample coverage differs")
    for path in (root / "01_Manuscript").glob("*.docx"):
        with ZipFile(path) as document:
            require(document.testzip() is None, "Invalid manuscript ZIP: " + path.name)
    links = verify_navigation(root)
    require(not any(path.is_symlink() for path in root.rglob("*")), "Package contains a symbolic link")
    counts = Counter(item["status"] for item in positions)
    return {
        "stage": stage, "sealed_files": file_count, "hashes": "passed",
        "positions": len(positions), "parseable_databases": counts["parseable_database"],
        "partial_raw_texts": counts["partial_raw_text"], "terminal_zeros": counts["terminal_zero"],
        "prediction_cells_reconciled": cells, "reference_files": len(references),
        "source_files": len(sources), "human_returns": {"A": sample, "B": sample},
        "current_navigation_links": links, "external_symlinks": 0, "status": "passed",
    }

def main(argv=None, *, default_root=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact-root", type=Path, default=default_root, required=default_root is None)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args(argv)
    try:
        result = verify_materials(args.artifact_root)
    except (OSError, ValueError, KeyError, TypeError, BadZipFile) as error:
        parser.exit(1, "Validation error: " + str(error) + "\n")
    if args.out:
        args.out.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))
    return result

if __name__ == "__main__":
    main()

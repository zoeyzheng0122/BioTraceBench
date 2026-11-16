"""Offline, task-local material preparation with complete PDF attachment pages.

Text representations preserve markup; Office tables retain spans, formatting and
cell addresses. Images remain native resolution. Optional readers are explicit.
"""
import base64
import csv
import importlib.metadata
import io
import json
import posixpath
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path
from decimal import Decimal
from xml.etree import ElementTree as ET

from .common import Stop, digest, encoded, read, seal, sha, verify, within, write
from .schema import check_schema
from .embedded import object_references, prism_object
from . import dataset_identity
from .material_selection import PDF_POLICY, select_materials, article_pdf, main_representation, roles
from .pdf_material import prepare_pdf, validate_pdf

TEXT = {".txt", ".md", ".csv", ".tsv", ".json", ".xml", ".html"}
IMAGE = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".tif", ".tiff"}
OFFICE = {".docx", ".pptx", ".xlsx", ".xls"}


def xml(data):
    if b"<!ENTITY" in data.upper():
        raise Stop("blocked_format", "XML entity declarations are not supported")
    return ET.fromstring(data)


def office_projection(name, tree):
    """Readable paragraphs/tables, with exact OOXML parts available separately."""
    def local(tag):
        return tag.split("}")[-1]
    def paragraph(node):
        text = []
        refs, properties = [], []
        for child in node.iter():
            kind = local(child.tag)
            if kind in {"t", "delText", "instrText"}:
                text.append(child.text or "")
            elif kind == "tab":
                text.append("\t")
            elif kind in {"br", "cr"}:
                text.append("\n")
            if kind in {"blip", "imagedata", "footnoteReference", "endnoteReference", "hyperlink"}:
                refs.append({"type": kind, "attributes": child.attrib})
            if kind in {"pStyle", "numPr", "ins", "del", "vertAlign"}:
                properties.append({"type": kind, "xml": ET.tostring(child, encoding="unicode")})
        return {"text": "".join(text), "references": refs, "properties": properties}
    def table(node):
        rows = []
        for row in node:
            if local(row.tag) != "tr":
                continue
            cells = []
            for cell in row:
                if local(cell.tag) != "tc":
                    continue
                properties = [{"type": local(c.tag), "attributes": c.attrib} for c in cell.iter()
                              if local(c.tag) in {"gridSpan", "vMerge", "hMerge", "tcW", "rowSpan"}]
                cells.append({"paragraphs": [paragraph(p) for p in cell if local(p.tag) == "p"],
                              "nested_tables": [table(t) for t in cell if local(t.tag) == "tbl"],
                              "merge_and_width": properties, "attributes": cell.attrib})
            rows.append(cells)
        return {"rows": rows, "attributes": node.attrib}
    if name.endswith(".rels"):
        return [{"part": name, "relationships": [{**c.attrib} for c in tree]}]
    if re.fullmatch(r"word/(document|footnotes|endnotes|comments|header\d+|footer\d+)\.xml", name) or re.fullmatch(r"ppt/(slides/slide\d+|notesSlides/notesSlide\d+)\.xml", name):
        blocks = []
        def walk(node, location, ancestry=None):
            ancestry = list(ancestry or [])
            if node.attrib:
                ancestry.append({"element": local(node.tag), "attributes": node.attrib})
            kind = local(node.tag)
            if kind == "tbl":
                blocks.append({"part": name, "locator": location, "context": ancestry, "table": table(node)})
                return
            if kind == "p":
                blocks.append({"part": name, "locator": location, "context": ancestry, "paragraph": paragraph(node)})
                return
            for i, child in enumerate(node):
                walk(child, location + "/" + local(child.tag) + f"[{i}]", ancestry)
        walk(tree, "/" + local(tree.tag))
        return blocks
    if name.startswith(("word/charts/", "ppt/charts/")):
        return [{"part": name, "chart_xml": ET.tostring(tree, encoding="unicode")}]
    return [{"part": name, "note": "Formatting/metadata retained in source; read_office_part provides exact XML on demand"}]


def office_convert(source, destination, kind, office_bin):
    if not office_bin or not Path(office_bin).is_file():
        raise Stop("blocked_dependency", "Existing LibreOffice executable required for WMF/EMF or XLS")
    if source.suffix.lower() == ".pdf" or kind not in {"png", "xlsx"}:
        raise Stop("blocked_format", "Use the dedicated PDF reader; Office conversion supports images and workbooks")
    destination.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="biotracebench-office-") as temp:
        profile = Path(temp) / "profile"
        profile.mkdir()
        # Prevent source documents from running macros or refreshing external links.
        (profile / "registrymodifications.xcu").write_text(
            '<?xml version="1.0"?><oor:items xmlns:oor="http://openoffice.org/2001/registry">'
            '<item oor:path="/org.openoffice.Office.Common/Security/Scripting">'
            '<prop oor:name="MacroSecurityLevel" oor:op="fuse"><value>3</value></prop></item>'
            '</oor:items>')
        command = [str(office_bin), "-env:UserInstallation=" + profile.as_uri(),
                   "--headless", "--norestore", "--nodefault", "--convert-to",
                   "png:draw_png_Export" if kind == "png" else "xlsx:Calc MS Excel 2007 XML",
                   "--outdir", str(destination), str(source)]
        result = subprocess.run(command, capture_output=True, text=True, timeout=120)
        target = destination / (source.stem + "." + kind)
        if result.returncode or not target.is_file():
            raise Stop("blocked_conversion", "Office conversion did not produce " + target.name)
        return target


def images(source, folder, origin, office_bin=None):
    try:
        from PIL import Image, ImageSequence
    except ImportError:
        raise Stop("blocked_dependency", "Pillow is required to validate images") from None
    original = source
    if source.suffix.lower() in {".wmf", ".emf"}:
        source = office_convert(source, folder / "converted", "png", office_bin)
    with Image.open(source) as image:
        image.verify()
    records = []
    with Image.open(source) as image:
        for i, frame in enumerate(ImageSequence.Iterator(image)):
            frame.load()
            target = folder / f"image-{len(list(folder.glob('image-*'))):05d}.png"
            frame.convert("RGBA" if "A" in frame.getbands() else "RGB").save(target, format="PNG")
            records.append({"path": target.name, "origin": origin, "frame": i,
                            "source_sha256": sha(original), "sha256": sha(target),
                            "width": frame.width, "height": frame.height, "bytes": target.stat().st_size, "mime": "image/png"})
    return records


def workbook(source, folder, db, material_id, office_bin):
    try:
        import openpyxl
    except ImportError:
        raise Stop("blocked_dependency", "openpyxl is required for workbook indexing") from None
    declared_legacy = source.suffix.lower() == ".xls"
    native_ooxml = False
    if declared_legacy and zipfile.is_zipfile(source):
        with zipfile.ZipFile(source) as archive:
            native_ooxml = "xl/workbook.xml" in archive.namelist()
        if not native_ooxml:
            raise Stop("blocked_format", "XLS-labelled ZIP is not an OOXML workbook")
    converted = declared_legacy and not native_ooxml
    if converted:
        source = office_convert(source, folder / "converted", "xlsx", office_bin)
    parse_source, normalizations = source, []
    if native_ooxml:
        # Some publishers label an existing OOXML workbook .xls. Read its bytes
        # directly via a correctly suffixed copy; conversion can change formulas,
        # styles and merge notation and is unnecessary for this container.
        parse_source = folder / "reader-native.xlsx"
        shutil.copyfile(source, parse_source)
    if converted:
        # LibreOffice can encode full-row/column merges (e.g. 4:4). openpyxl
        # rejects that valid shorthand. Expand only the range syntax in a separate
        # derived reader copy, retaining both original XLS and converted OOXML.
        parse_source = folder / "converted" / "reader-compatible.xlsx"
        with zipfile.ZipFile(source) as original, zipfile.ZipFile(parse_source, "w", compression=zipfile.ZIP_DEFLATED) as normalized:
            for info in original.infolist():
                data = original.read(info.filename)
                if re.fullmatch(r"xl/worksheets/sheet\d+\.xml", info.filename):
                    def expand(match):
                        ref = match[1].decode()
                        replacement = ref
                        if re.fullmatch(r"\d+:\d+", ref):
                            start, end = ref.split(":")
                            replacement = "A"+start+":XFD"+end
                        elif re.fullmatch(r"[A-Z]+:[A-Z]+", ref):
                            start, end = ref.split(":")
                            replacement = start+"1:"+end+"1048576"
                        if replacement != ref:
                            normalizations.append({"part": info.filename, "original": ref, "equivalent_range": replacement})
                        return b'<mergeCell ref="'+replacement.encode()+b'"'
                    data = re.sub(rb'<mergeCell ref="([^"]+)"', expand, data)
                normalized.writestr(info, data)
    formulas = openpyxl.load_workbook(parse_source, read_only=True, data_only=False, keep_links=False)
    values = openpyxl.load_workbook(parse_source, read_only=True, data_only=True, keep_links=False)
    sheets = []
    with zipfile.ZipFile(source) as exact, (folder / "content.txt").open("w", encoding="utf-8") as text:
        ns = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
        relations = {r.attrib["Id"]: r.attrib["Target"] for r in xml(exact.read("xl/_rels/workbook.xml.rels"))}
        parts = {}
        for node in xml(exact.read("xl/workbook.xml")).findall("s:sheets/s:sheet", ns):
            target = relations[node.attrib["{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"]]
            parts[node.attrib["name"]] = target.lstrip("/") if target.startswith("/") else posixpath.normpath(posixpath.join("xl", target))
        def numeric_rows(part):
            # A streaming companion retains numeric literals which Python's float
            # conversion would round. No scientific tolerance or unit rule applies.
            with exact.open(part) as stream:
                for _, node in ET.iterparse(stream, events=("end",)):
                    if node.tag == "{" + ns["s"] + "}row":
                        numbers = {}
                        for cell in node.findall("s:c", ns):
                            value = cell.find("s:v", ns)
                            if cell.attrib.get("t", "n") == "n" and value is not None and value.text is not None:
                                numbers[cell.attrib["r"]] = value.text
                        yield int(node.attrib["r"]), numbers
                        node.clear()
        for sheet, cached in zip(formulas.worksheets, values.worksheets):
            rows, cols = 0, 0
            numeric = numeric_rows(parts[sheet.title])
            numeric_row, literals = next(numeric, (0, {}))
            for a, b in zip(sheet.iter_rows(), cached.iter_rows()):
                nonempty = []
                for cell, value in zip(a, b):
                    if cell.value is None:
                        continue
                    # Dates retain their ISO value and Excel display format. No scientific conversions.
                    original = cell.value.isoformat() if hasattr(cell.value, "isoformat") else cell.value
                    cache = value.value.isoformat() if hasattr(value.value, "isoformat") else value.value
                    record = {"cell": cell.coordinate, "raw": original, "cached": cache,
                              "number_format": cell.number_format, "is_formula": cell.data_type == "f"}
                    while numeric_row < cell.row:
                        numeric_row, literals = next(numeric, (cell.row, {}))
                    literal = literals.get(cell.coordinate) if numeric_row == cell.row else None
                    if literal is not None and any(type(v) in {int, float} and Decimal(str(v)) != Decimal(literal)
                                                   for v in (original, cache)):
                        record["source_numeric_lexeme"] = literal
                    db.execute("INSERT INTO cells VALUES (?,?,?,?,?,?)",
                               (material_id, sheet.title, cell.row, cell.column, cell.coordinate, encoded(record).decode()))
                    nonempty.append(record)
                    rows, cols = max(rows, cell.row), max(cols, cell.column)
                if nonempty:
                    text.write(encoded({"sheet": sheet.title, "row": rows, "cells": nonempty}).decode() + "\n")
            sheets.append({"name": sheet.title, "rows": rows, "columns": cols})
            numeric.close()
        # Read-only worksheets omit merge ranges; retain them directly from the OOXML parts.
        with zipfile.ZipFile(source) as archive:
            for name in archive.namelist():
                if re.fullmatch(r"xl/worksheets/sheet\d+\.xml", name):
                    with archive.open(name) as stream:
                        for _, node in ET.iterparse(stream, events=("end",)):
                            if node.tag.endswith("}mergeCell"):
                                text.write(encoded({"xml_part": name, "merged_range": node.attrib["ref"]}).decode() + "\n")
                            node.clear()
    formulas.close()
    values.close()
    return {"sheets": sheets, "legacy_conversion": converted, "conversion_sha256": sha(source) if converted else None,
            "detected_workbook_container": "ooxml", "native_ooxml_with_legacy_extension": native_ooxml,
            "numeric_representation": "raw/cached reader values; source_numeric_lexeme preserves the exact source number when binary float would round it (cached value for a formula)",
            "reader_range_normalizations": normalizations}


def prepare(dataset, case_id, output, *, office_bin=None, selection_manifest=None,
            delivery_policy=None, from_prepared=None):
    if selection_manifest or delivery_policy or from_prepared:
        if not selection_manifest or not delivery_policy:
            raise ValueError("Shared preparation requires selection_manifest and delivery_policy")
        from .shared_inputs import prepare as shared_prepare
        return shared_prepare(dataset, case_id, output, selection_manifest=selection_manifest,
                              delivery_policy=delivery_policy, from_prepared=from_prepared, office_bin=office_bin)
    if not re.fullmatch(r"[BC]\d{3}", case_id):
        raise ValueError("Expected Bnnn or Cnnn task ID")
    root, output = Path(dataset).resolve(), Path(output).resolve()
    domain = "basic" if case_id.startswith("B") else "clinical"
    task_dir = root / "tasks" / domain / case_id
    material_dir = root / "materials" / domain / case_id
    if output.exists():
        raise Stop("already_exists", "Use a new preparation directory")
    if output.is_relative_to(root):
        raise Stop("blocked_path", "Source dataset is read-only")
    output.mkdir(parents=True)
    task, paths = dataset_identity.task_sources(root, case_id, domain)
    if task.get("case_id") != case_id or task.get("domain") != domain:
        raise Stop("blocked_identity", "Task identity mismatch")
    manifest = read(paths["materials_manifest"])
    if manifest["case"]["case_id"] != case_id:
        raise Stop("blocked_identity", "Material identity mismatch")
    prompt = paths["complete_prompt"].read_text()
    schema = read(paths["schema"])
    check_schema(schema)
    dictionary = read(paths["field_dictionary"])[domain]
    origin = dataset_identity.capture(root, case_id, domain)
    write(output / "source-identity.json", origin)
    write(output / "task.json", task)
    write(output / "schema.json", schema)
    write(output / "dictionary.json", dictionary)
    (output / "instruction.md").write_text(prompt, encoding="utf-8")
    db = sqlite3.connect(output / "cells.sqlite")
    db.execute("CREATE TABLE cells (material TEXT, sheet TEXT, row INTEGER, col INTEGER, coordinate TEXT, data TEXT)")
    db.execute("CREATE INDEX cell_range ON cells(material,sheet,row,col)")
    report = {"protocol": dataset_identity.PREPARATION, "case_id": case_id, "domain": domain,
              "dataset_identity": origin["dataset"]["identity"], "source_identity": origin["identity"],
              "study_id": task.get("study_id") or task["doi"], "pdf_policy": PDF_POLICY,
              "manifest_sha256": sha(paths["materials_manifest"]),
              "manifest_path": str(paths["materials_manifest"].relative_to(root)), "materials": [], "excluded": [],
              "errors": [], "python": sys.version.split()[0], "parsers": {}, "preparer_sha256": sha(__file__)}
    for package in ("Pillow", "openpyxl", "pypdfium2"):
        try:
            report["parsers"][package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            report["parsers"][package] = None
    if office_bin and Path(office_bin).is_file():
        version = subprocess.run([str(office_bin), "--version"], capture_output=True, text=True, timeout=30)
        report["office_converter"] = {"path": str(office_bin), "version": version.stdout.strip(), "returncode": version.returncode}
    # Selection precedes open(), stat(), copy(), hashing or decoding of exclusions.
    selected, report["excluded"] = select_materials(manifest["files"])
    seen = set()
    for item in selected:
        relative = item["path"]
        record = {"id": f"m{len(report['materials']) + 1:04d}", "source": relative,
                  "role": item.get("role"), "roles": sorted(roles(item)), "images": [], "status": "pending"}
        report["materials"].append(record)
        folder = output / record["id"]
        folder.mkdir()
        try:
            if relative in seen:
                raise Stop("blocked_manifest", "Duplicate material path")
            seen.add(relative)
            source = within(material_dir, relative)
            suffix = source.suffix.lower()
            if suffix == ".pdf" and (Path(relative).suffix.lower() != ".pdf" or article_pdf(item)):
                raise Stop("blocked_pdf", "Material alias cannot bypass article PDF selection")
            if suffix not in TEXT | IMAGE | OFFICE | {".pdf"}:
                raise Stop("blocked_format", "Unsupported material format: " + suffix)
            with source.open("rb") as stream:
                if stream.read(5) == b"%PDF-" and suffix != ".pdf":
                    raise Stop("blocked_pdf", "PDF content requires an explicitly declared PDF attachment")
            # Unsupported embedded objects block the container instead of being omitted.
            if suffix in OFFICE and zipfile.is_zipfile(source):
                with zipfile.ZipFile(source) as archive:
                    if any(Path(name).suffix.lower() == ".pdf" for name in archive.namelist()):
                        raise Stop("blocked_format", "Unsupported embedded PDF member in Office document")
            if sha(source) != item["sha256"] or source.stat().st_size != item["bytes"]:
                raise Stop("blocked_identity", "Material size or checksum mismatch")
            frozen = folder / ("source" + suffix)
            shutil.copyfile(source, frozen)
            record.update(sha256=item["sha256"], bytes=item["bytes"], format=suffix)
            if suffix == ".pdf":
                record.update(prepare_pdf(frozen, folder, relative))
            elif suffix in TEXT:
                content = source.read_text(encoding="utf-8-sig")
                if suffix == ".json":
                    json.loads(content)
                if suffix == ".xml":
                    tree = xml(source.read_bytes())
                    record["elements"] = sum(1 for _ in tree.iter())
                if suffix in {".csv", ".tsv"}:
                    record["rows"] = sum(1 for _ in csv.reader(io.StringIO(content), delimiter="\t" if suffix == ".tsv" else ","))
                (folder / "content.txt").write_text(content, encoding="utf-8")
            elif suffix in IMAGE:
                record["images"] = images(frozen, folder, relative, office_bin)
            elif suffix in {".xlsx", ".xls"}:
                record.update(workbook(frozen, folder, db, record["id"], office_bin))
                workbook_source = folder / "converted" / "source.xlsx" if record["legacy_conversion"] else frozen
                with zipfile.ZipFile(workbook_source) as archive:
                    for name in archive.namelist():
                        if name.startswith("xl/media/"):
                            target = folder / ("embedded-" + Path(name).name)
                            target.write_bytes(archive.read(name))
                            record["images"].extend(images(target, folder, relative + "#" + name, office_bin))
                        elif name.startswith("xl/embeddings/"):
                            raise Stop("blocked_format", "Embedded Excel object needs explicit support: " + name)
                        elif name.startswith(("xl/drawings/", "xl/comments")) and name.endswith((".xml", ".rels")):
                            with (folder / "content.txt").open("a") as text:
                                text.write(encoded({"xml_part": name, "xml": archive.read(name).decode("utf-8-sig")}).decode()+"\n")
            else:
                with zipfile.ZipFile(frozen) as archive:
                    bad = archive.testzip()
                    if bad:
                        raise Stop("blocked_format", "Corrupt Office member")
                    parts = []
                    embedded = []
                    objects = []
                    object_refs = object_references(archive)
                    for name in archive.namelist():
                        if name.endswith("/"):
                            continue
                        if name.startswith(("word/", "ppt/")) and name.endswith((".xml", ".rels")):
                            data = archive.read(name)
                            tree = xml(data)
                            parts.extend(office_projection(name, tree))
                        if name.startswith(("word/media/", "ppt/media/")):
                            target = folder / ("embedded-" + Path(name).name)
                            target.write_bytes(archive.read(name))
                            record["images"].extend(images(target, folder, relative + "#" + name, office_bin))
                            embedded.append(name)
                        if name.startswith(("word/embeddings/", "ppt/embeddings/")):
                            refs = object_refs.get(name, [])
                            if not refs or any(ref["program_id"] != "Prism10.Document" for ref in refs):
                                raise Stop("blocked_format", "Unsupported embedded object: " + name)
                            obj, blocks = prism_object(archive.read(name), folder / f"object-{len(objects):05d}",
                                                       name, refs)
                            objects.append(obj)
                            parts.extend(blocks)
                    for obj in objects:
                        preview_parts = {p for ref in obj["references"] for p in ref["preview_parts"]}
                        obj["preview_image_indices"] = [i for i, image in enumerate(record["images"])
                                                        if image["origin"] in {relative + "#" + p for p in preview_parts}]
                        if not obj["preview_image_indices"]:
                            raise Stop("blocked_format", "Embedded object has no readable linked preview")
                        # The member list makes retained binary limitations visible to
                        # the model alongside all native JSON/CSV and linked images.
                        parts.append({"embedded_object": obj})
                    (folder / "content.txt").write_text("\n".join(encoded(p).decode() for p in parts), encoding="utf-8")
                    record.update(parts=sorted({p["part"] for p in parts if "part" in p}),
                                  embedded_images=embedded, embedded_objects=objects)
            text = folder / "content.txt"
            characters = 0
            if text.exists():
                with text.open(newline="") as stream:
                    for piece in iter(lambda: stream.read(65536), ""):
                        characters += len(piece)
            record["text_characters"] = characters
            record["text_bytes"] = text.stat().st_size if text.exists() else 0
            record["status"] = "readable"
        except (ValueError, TypeError, OSError, Stop, zipfile.BadZipFile, ET.ParseError, subprocess.TimeoutExpired) as exc:
            record["status"] = "blocked"
            record["error"] = str(exc)
            report["errors"].append({"source": relative, "error": str(exc)})
    db.commit()
    db.close()
    if not any(main_representation({**x, "path": x["source"]}) and x["status"] == "readable"
               for x in report["materials"]):
        report["errors"].append({"error": "No readable XML or HTML main article representation"})
    report["status"] = "blocked" if report["errors"] else "ready_offline"
    report["live_api_verified"] = False
    effective_input = {"protocol": "biotracebench-effective-inputs-1", "case_id": case_id,
                       "dataset_identity": report["dataset_identity"], "source_identity": report["source_identity"],
                       "pdf_policy": report["pdf_policy"], "included": report["materials"], "excluded": report["excluded"],
                       "format_counts": {fmt: sum(m.get("format") == fmt for m in report["materials"])
                                         for fmt in sorted({m["format"] for m in report["materials"] if m.get("format")})},
                       "evidence_coverage": "not_scientifically_verified",
                       "meaning": "Complete available representations, not a claim that excluded sources add no necessary facts."}
    write(output / "effective-inputs.json", effective_input)
    write(output / "materials.json", report)
    seal(output)
    return report


class Reader:
    def __init__(self, folder, expected=None):
        self.folder = Path(folder).resolve()
        self.manifest = read(self.folder / "materials.json")
        if self.manifest.get("pdf_policy") != PDF_POLICY:
            raise Stop("stale_preparation", "Prepare materials again using the current PDF selection policy")
        self.entries = {x["id"]: x for x in self.manifest["materials"]}
        allowed = set()
        for mid, entry in self.entries.items():
            if not re.fullmatch(r"m[0-9]{4,}", mid):
                raise Stop("blocked_materials", "Invalid prepared material identifier")
            if entry.get("format") == ".pdf" and not self.manifest.get("shared_inputs"):
                if article_pdf({**entry, "path": entry["source"]}):
                    raise Stop("blocked_pdf", "Main article PDF cannot enter prepared inputs")
                allowed.add(self.folder / mid / "source.pdf")
        # Reject unlisted PDF payloads before receipt verification could hash them.
        if any(p not in allowed for p in self.folder.rglob("*") if p.suffix.lower() == ".pdf"):
            raise Stop("blocked_pdf", "Unlisted PDF payload in prepared materials")
        self.identity = verify(self.folder, expected)
        if self.manifest["status"] != "ready_offline":
            raise Stop("blocked_materials", "Prepared materials contain unreadable files")
        if self.manifest.get("shared_inputs"):
            from .shared_inputs import validate as validate_shared
            validate_shared(self)
        else:
            for mid, entry in self.entries.items():
                if entry.get("format") == ".pdf":
                    validate_pdf(entry, self.folder / mid)

    def listing(self):
        return [{k: v for k, v in e.items() if k not in {"sha256"}} for e in self.entries.values()]

    def text(self, material, offset, limit):
        if material not in self.entries or type(offset) is not int or offset < 0 or type(limit) is not int or limit < 1:
            raise ValueError("Invalid material or character range")
        path = self.folder / material / "content.txt"
        if not path.exists():
            raise ValueError("This material is an image; use view_image")
        # Read incrementally, without loading an 83 MB workbook projection into RAM.
        with path.open(encoding="utf-8", newline="") as stream:
            left = offset
            while left:
                piece = stream.read(min(left, 65536))
                if not piece:
                    break
                left -= len(piece)
            result = stream.read(limit)
        return {"material": material, "offset": offset, "end": offset + len(result),
                "total_characters": self.entries[material]["text_characters"], "text": result}

    def search(self, query, limit=20, offset=0):
        if not isinstance(query, str) or not query.strip():
            raise ValueError("Nonempty literal search required")
        if type(offset) is not int or offset < 0:
            raise ValueError("Invalid search cursor")
        matches, seen = [], 0
        pattern = re.compile(re.escape(query), re.IGNORECASE)
        for material, entry in self.entries.items():
            path = self.folder / material / "content.txt"
            if not path.exists():
                continue
            position = 0
            with path.open() as stream:
                for line in stream:
                    for match in pattern.finditer(line):
                        seen += 1
                        if seen <= offset:
                            continue
                        if len(matches) >= limit:
                            return {"matches": matches, "limited": True, "next_offset": offset+len(matches)}
                        pos = match.start()
                        matches.append({"material": material, "offset": position + pos,
                                        "snippet": line[max(0, pos - 100):match.end() + 200]})
                    position += len(line)
        return {"matches": matches, "limited": False, "next_offset": None}

    def cells(self, material, sheet, row_start, row_end, col_start, col_end, limit):
        if material not in self.entries or "sheets" not in self.entries[material]:
            raise ValueError("Not a workbook")
        if not (1 <= row_start <= row_end and 1 <= col_start <= col_end) or (row_end-row_start+1)*(col_end-col_start+1) > limit:
            raise ValueError("Requested cell range exceeds explicit per-tool limit")
        with sqlite3.connect((self.folder / "cells.sqlite").as_uri() + "?mode=ro", uri=True) as db:
            rows = db.execute("SELECT data FROM cells WHERE material=? AND sheet=? AND row BETWEEN ? AND ? AND col BETWEEN ? AND ? ORDER BY row,col",
                              (material, sheet, row_start, row_end, col_start, col_end))
            return [json.loads(row[0]) for row in rows]

    def image(self, material, index):
        image = self.entries[material]["images"][index]
        path = within(self.folder / material, image["path"])
        if sha(path) != image["sha256"]:
            raise Stop("tampered", "Image changed")
        return image, "data:image/png;base64," + base64.b64encode(path.read_bytes()).decode()

    def office_part(self, material, part, offset, length):
        entry = self.entries[material]
        if entry["format"] not in {".docx", ".pptx", ".xlsx", ".xls"} or not part.endswith((".xml", ".rels")):
            raise ValueError("Only XML parts of the frozen Office document may be read")
        if type(offset) is not int or offset < 0 or type(length) is not int or length < 1:
            raise ValueError("Invalid XML character range")
        source = self.folder / material / ("source" + entry["format"])
        if entry.get("legacy_conversion"):
            source = self.folder / material / "converted" / "source.xlsx"
        with zipfile.ZipFile(source) as archive:
            if part not in archive.namelist():
                raise ValueError("Unknown Office part")
            with archive.open(part) as raw, io.TextIOWrapper(raw, encoding="utf-8-sig") as stream:
                remaining = offset
                while remaining:
                    chunk = stream.read(min(65536, remaining))
                    if not chunk:
                        break
                    remaining -= len(chunk)
                text = stream.read(length)
        return {"material": material, "part": part, "offset": offset, "end": offset+len(text), "text": text}

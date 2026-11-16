"""Read explicit Prism 10 OLE payloads without executing embedded software.

Scientific tables and metadata are provided verbatim as CSV/JSON. Native drawing
binaries remain archived and are represented visually by the linked Office image;
they are never described as semantically decoded. Unknown objects fail closed.
"""
import csv
import hashlib
import io
import json
import posixpath
import struct
import zipfile
from pathlib import PurePosixPath
from xml.etree import ElementTree as ET

from .common import Stop, encoded

END = 0xFFFFFFFE
FREE = 0xFFFFFFFF


def compound_streams(data):
    """Read flat CFB v3/v4 streams, including mini streams, with bounded chains."""
    def invalid(message):
        raise Stop("blocked_format", "Invalid embedded compound file: " + message)
    if len(data) < 512 or data[:8] != bytes.fromhex("d0cf11e0a1b11ae1"):
        invalid("signature")
    u16 = lambda at: struct.unpack_from("<H", data, at)[0]
    u32 = lambda at: struct.unpack_from("<I", data, at)[0]
    major, shift = u16(26), u16(30)
    if u16(28) != 0xFFFE or (major, shift) not in {(3, 9), (4, 12)} or u16(32) != 6:
        invalid("unsupported header")
    size = 1 << shift
    count = len(data) // size - 1
    if len(data) % size or u32(56) != 4096:
        invalid("length or mini-stream cutoff")
    def sector(sid):
        if not 0 <= sid < count:
            invalid("sector outside container")
        return data[(sid + 1) * size:(sid + 2) * size]
    def ints(raw):
        return list(struct.unpack("<" + str(len(raw) // 4) + "I", raw))
    fat_ids = [v for v in ints(data[76:512]) if v != FREE]
    sid, seen = u32(68), set()
    for _ in range(u32(72)):
        if sid in seen or len(seen) >= count:
            invalid("cyclic DIFAT")
        seen.add(sid)
        row = ints(sector(sid))
        fat_ids.extend(v for v in row[:-1] if v != FREE)
        sid = row[-1]
    if len(fat_ids) != u32(44) or len(set(fat_ids)) != len(fat_ids):
        invalid("FAT count")
    fat = [v for sid in fat_ids for v in ints(sector(sid))]
    def chain(first, table, fetch, limit):
        sid, seen, parts = first, set(), []
        while sid != END:
            if sid in seen or not 0 <= sid < len(table) or len(seen) >= limit:
                invalid("cyclic or invalid stream chain")
            seen.add(sid)
            parts.append(fetch(sid))
            sid = table[sid]
        return b"".join(parts)
    regular = lambda first: chain(first, fat, sector, count)
    directory = regular(u32(48))
    entries = []
    for at in range(0, len(directory), 128):
        row = directory[at:at + 128]
        kind = row[66]
        if kind == 0:
            continue
        length = struct.unpack_from("<H", row, 64)[0]
        if length < 2 or length > 64 or length % 2 or row[length-2:length] != b"\0\0":
            invalid("directory name")
        name = row[:length-2].decode("utf-16-le")
        if kind not in {2, 5}:
            invalid("nested storage not supported by this explicit reader")
        nbytes = struct.unpack_from("<Q", row, 120)[0]
        if major == 3:
            nbytes &= 0xFFFFFFFF
        if nbytes > len(data):
            invalid("stream length")
        entries.append((name, kind, struct.unpack_from("<I", row, 116)[0], nbytes))
    roots = [e for e in entries if e[1] == 5]
    if len(roots) != 1:
        invalid("root count")
    root = roots[0]
    mini_data = regular(root[2])[:root[3]] if root[3] else b""
    mini_fat = ints(regular(u32(60))) if u32(64) else []
    if len(mini_fat) != u32(64) * size // 4:
        invalid("mini FAT count")
    def mini_sector(sid):
        if sid * 64 + 64 > len(mini_data):
            invalid("mini sector outside root")
        return mini_data[sid * 64:(sid + 1) * 64]
    streams = {}
    for name, kind, first, nbytes in entries:
        if kind != 2:
            continue
        if name in streams:
            invalid("duplicate stream")
        raw = (chain(first, mini_fat, mini_sector, len(mini_data) // 64)
               if nbytes < 4096 else regular(first)) if nbytes else b""
        if len(raw) < nbytes:
            invalid("truncated stream")
        streams[name] = raw[:nbytes]
    return streams


def object_references(archive):
    """Map each embedded payload to its slide/paragraph and linked previews."""
    result = {}
    for part in archive.namelist():
        if not part.startswith(("word/", "ppt/")) or not part.endswith(".xml"):
            continue
        data = archive.read(part)
        if b"<!ENTITY" in data.upper():
            raise Stop("blocked_format", "Embedded XML entity declaration")
        tree = ET.fromstring(data)
        nodes = [e for e in tree.iter() if e.tag.rsplit("}", 1)[-1] == "oleObj"]
        if not nodes:
            continue
        parent, filename = posixpath.split(part)
        rel_part = parent + "/_rels/" + filename + ".rels"
        if rel_part not in archive.namelist():
            raise Stop("blocked_format", "Missing embedded-object relationships")
        rel_data = archive.read(rel_part)
        if b"<!ENTITY" in rel_data.upper():
            raise Stop("blocked_format", "Embedded relationship entity declaration")
        relations = {e.attrib["Id"]: e.attrib for e in ET.fromstring(rel_data)}
        def target(identifier):
            relation = relations.get(identifier, {})
            if not relation.get("Target") or relation.get("TargetMode") == "External":
                raise Stop("blocked_format", "Embedded object must have a local relationship")
            path = posixpath.normpath(posixpath.join(parent, relation["Target"]))
            if path.startswith(("../", "/")) or path not in archive.namelist():
                raise Stop("blocked_format", "Invalid embedded-object target")
            return path
        for node in nodes:
            identifier = node.attrib.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id")
            payload = target(identifier)
            previews = sorted({target(e.attrib["{http://schemas.openxmlformats.org/officeDocument/2006/relationships}embed"])
                               for e in node.iter() if e.tag.rsplit("}", 1)[-1] == "blip"
                               and "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}embed" in e.attrib})
            row = {"part": part, "relationship_id": identifier,
                   "program_id": node.attrib.get("progId"), "preview_parts": previews}
            if row not in result.setdefault(payload, []):
                result[payload].append(row)
    return result


def prism_object(data, folder, part, references):
    if not references or any(r["program_id"] != "Prism10.Document" for r in references):
        raise Stop("blocked_format", "Unsupported embedded object: " + part)
    if not any(r["preview_parts"] for r in references):
        raise Stop("blocked_format", "Prism object requires an explicit linked preview")
    streams = compound_streams(data)
    if "CONTENTS" not in streams or any(n not in {"CONTENTS", "\x01Ole", "\x01CompObj", "\x02OlePres000", "\x02OlePres001"} for n in streams):
        raise Stop("blocked_format", "Unknown Prism compound stream")
    payload = streams["CONTENTS"]
    if len(payload) < 8 or payload[4:8] != b"PK\x03\x04" or struct.unpack_from("<I", payload)[0] not in {len(payload), len(payload)-4}:
        raise Stop("blocked_format", "Unknown Prism native payload")
    folder.mkdir()
    (folder / "source.bin").write_bytes(data)
    (folder / "source.prism").write_bytes(payload[4:])
    records, blocks, tables = [], [], []
    with zipfile.ZipFile(io.BytesIO(payload[4:])) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)) or sum(i.file_size for i in archive.infolist()) > 32 * 1024 * 1024:
            raise Stop("blocked_format", "Duplicate or oversized Prism archive")
        for info in archive.infolist():
            name = info.filename
            path = PurePosixPath(name)
            if path.is_absolute() or ".." in path.parts or "\\" in name or info.flag_bits & 1:
                raise Stop("blocked_format", "Invalid Prism member")
            if name.lower().endswith(".pdf"):
                raise Stop("blocked_format", "Unsupported embedded PDF member in Prism object")
            if info.is_dir():
                continue
            raw = archive.read(name)
            row = {"member": name, "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
            if name.endswith((".json", ".csv")):
                text = raw.decode("utf-8-sig")
                if name.endswith(".json"):
                    json.loads(text)
                    row["representation"] = "verbatim_json"
                else:
                    cells = list(csv.reader(io.StringIO(text)))
                    row.update(representation="verbatim_csv", rows=len(cells),
                               columns=max((len(r) for r in cells), default=0))
                    tables.append(row)
                blocks.append({"embedded_part": part, "native_member": name,
                               "representation": row["representation"], "text": text})
            elif name.endswith(".bin") and name.startswith(("graphs/", "misc/")) or name.endswith("/data.dt"):
                row["representation"] = "archived_binary_not_semantically_decoded"
            else:
                raise Stop("blocked_format", "Unknown Prism member type: " + name)
            records.append(row)
        if "document.json" not in names or not tables:
            raise Stop("blocked_format", "Prism document metadata or data table missing")
    # All native members are preserved in source.prism; graph binaries are not
    # scientific values inferred by this parser. Linked previews carry appearance.
    metadata = {"part": part, "reader": "prism10-json-csv-1", "references": references,
                "source_sha256": hashlib.sha256(data).hexdigest(),
                "native_archive_sha256": hashlib.sha256(payload[4:]).hexdigest(),
                "archive_path": str(folder.name + "/source.prism"), "members": records,
                "table_count": len(tables), "status": "data_and_linked_preview_readable",
                "binary_semantics": "not_decoded; original binaries retained; visual appearance supplied by linked Office previews"}
    (folder / "manifest.json").write_bytes(encoded(metadata))
    return metadata, blocks

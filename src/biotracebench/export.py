"""Dependency-free JSON/CSV/XLSX/HTML exports; never call a model."""
import csv
import html
import json
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape
from .common import read, verify, write
from model_conversation.archive import encoded, read_exact
from . import conditions


def display(value):
    return "" if value is None else encoded(value).decode() if isinstance(value, (dict, list)) else str(value)


def xlsx(path, tables):
    def xml(text):
        return '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>' + text
    with zipfile.ZipFile(path, "x", compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", xml('<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>' + ''.join(f'<Override PartName="/xl/worksheets/sheet{i}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>' for i in range(1, len(tables)+1)) + '</Types>'))
        z.writestr("_rels/.rels", xml('<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>'))
        z.writestr("xl/workbook.xml", xml('<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>' + ''.join(f'<sheet name="{escape(name)}" sheetId="{i}" r:id="rId{i}"/>' for i, name in enumerate(tables, 1)) + '</sheets></workbook>'))
        z.writestr("xl/_rels/workbook.xml.rels", xml('<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">' + ''.join(f'<Relationship Id="rId{i}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{i}.xml"/>' for i in range(1, len(tables)+1)) + '</Relationships>'))
        for i, (name, rows) in enumerate(tables.items(), 1):
            content = '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>'
            for n, row in enumerate(rows, 1):
                content += f'<row r="{n}">' + ''.join('<c t="inlineStr"><is><t xml:space="preserve">' + escape(display(v)) + '</t></is></c>' for v in row) + '</row>'
            z.writestr(f"xl/worksheets/sheet{i}.xml", xml(content + '</sheetData></worksheet>'))


def database(value, folder, dictionary=None):
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=False)
    write(folder / "database.json", value)
    tables, sections = {}, []
    if isinstance(value, dict):
        for name, rows in value.items():
            if not isinstance(rows, list):
                continue
            keys = [f["key"] for f in (dictionary or {}).get(name, {}).get("fields", [])]
            keys += sorted({k for row in rows if isinstance(row, dict) for k in row} - set(keys))
            values = [[row.get(k) for k in keys] for row in rows if isinstance(row, dict)]
            tables[name] = [keys] + values
            with (folder / (name + ".csv")).open("w", newline="", encoding="utf-8-sig") as stream:
                writer = csv.writer(stream)
                writer.writerow(keys)
                for row in values:
                    writer.writerow([("'" + display(v)) if isinstance(v, str) and v.startswith(("=", "+", "-", "@")) else display(v) for v in row])
            sections.append('<h2>' + html.escape(name) + '</h2><table><thead><tr>' + ''.join('<th>'+html.escape(k)+'</th>' for k in keys) + '</tr></thead><tbody>' + ''.join('<tr>'+''.join('<td>'+html.escape(display(v))+'</td>' for v in row)+'</tr>' for row in values) + '</tbody></table>')
    xlsx(folder / "tables.xlsx", tables or {"status": [["No usable database"]]})
    (folder / "index.html").write_text('<!doctype html><html lang="en"><meta charset="utf-8"><title>BioTraceBench tables</title><style>body{font:15px system-ui;margin:30px}table{border-collapse:collapse}td,th{border:1px solid #ccc;padding:8px;white-space:pre-wrap;vertical-align:top}</style><h1>BioTraceBench</h1><p>JSON contains the stored database values. CSV escapes formula prefixes. Excel uses text cells to prevent automatic conversion of scientific values.</p>' + ''.join(sections) + '</html>')


def run_report(run_dir, output):
    run_dir, output = Path(run_dir), Path(output)
    output.mkdir(parents=True, exist_ok=False)
    status = read(run_dir / "status.json")
    costs = read(run_dir / "costs.json")
    manifest = read(run_dir / "manifest.json")
    from model_conversation import Conversation
    identity = {"model": Conversation(manifest["model"]).describe(), "run_identity": manifest["identity"],
                "task_set_identity": manifest.get("task_set_identity"), "scoring_executed": False}
    write(output / "model-identity.json", identity)
    write(output / "condition-identity.json", conditions.identity(manifest))
    links = []
    for task in manifest["tasks"]:
        for stage in manifest["stages"]:
            final = run_dir / task["case_id"] / stage / "final"
            if final.exists():
                verify(final)
                destination = output / task["case_id"] / stage
                database(read_exact(final / "database.json"), destination, read(Path(task["prepared"]) / "dictionary.json"))
                if (final / "raw-answer.txt").exists():
                    (destination / "raw-answer.txt").write_bytes((final / "raw-answer.txt").read_bytes())
                write(destination / "diagnostics.json", read(final / "diagnostics.json"))
                if (final.parent / "initial-review-start.json").exists():
                    write(destination / "initial-review-start.json", read(final.parent / "initial-review-start.json"))
                assessment = None
                for name in ("output-assessment.json", "input-delivery.json", "annotations.json"):
                    if (final / name).exists():
                        write(destination / name, read(final / name))
                if (final / "output-assessment.json").exists():
                    assessment = read(final / "output-assessment.json")
                note = ''
                if assessment:
                    note = (' · Database schema valid' if assessment['database_schema_valid'] else ' · Database schema errors')
                    note += f' · Process diagnostics: {len(assessment["process_diagnostics"])} · Scientific correctness not scored'
                    note += f' · <a href="{task["case_id"]}/{stage}/output-assessment.json">Assessment record</a>'
                if (destination / "annotations.json").exists():
                    note += f' · <a href="{task["case_id"]}/{stage}/annotations.json">Evidence and notes</a>'
                links.append(f'<li><a href="{task["case_id"]}/{stage}/index.html">{task["case_id"]} / {conditions.label(manifest, stage)}</a>{note}</li>')
            else:
                links.append('<li>' + html.escape(task["case_id"] + ' / ' + conditions.label(manifest, stage) + ': ' + status["tasks"][task["case_id"]][stage]) + '</li>')
    from .limits import extensions
    write(output / "limit-extensions.json", extensions(manifest, run_dir))
    write(output / "status.json", status)
    write(output / "costs.json", costs)
    with (output / "costs.csv").open("w", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["case_id", "stage", "attempt", "amount", "currency", "basis", "budget_upper", "budget_basis"])
        for row in costs["calls"]:
            writer.writerow([row["case_id"], row["stage"], row["attempt"], row["amount"], costs["currency"], costs["basis"], row.get("budget_upper"), (row.get("cost") or {}).get("budget_basis")])
    banner = '<p style="padding:20px;background:#fff3cd">Synthetic demonstration: answers, tokens and costs are test fixtures. Real API calls: 0. Actual API cost: 0. This output is engineering test data.</p>' if manifest.get("synthetic") else ''
    (output / "index.html").write_text('<!doctype html><meta charset="utf-8"><title>BioTraceBench run</title><h1>BioTraceBench run</h1>' + banner + '<p>Model: ' + html.escape(manifest['model']['model']) + ' · generation only</p><ul>' + ''.join(links) + '</ul><h2>Cost ledger</h2><pre>' + html.escape(json.dumps(costs, ensure_ascii=False, indent=2)) + '</pre>')

"""Read archived submissions without repairing answers or inventing failures."""
import json
from decimal import Decimal
from pathlib import Path
from model_conversation.archive import read, verify, sha
from biotracebench.submission import evaluable_json

TERMINAL_FAILURES = {"failed", "failed_validation", "invalid_output", "failed_initial_submission"}


def strict_json(text):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("Duplicate JSON key requires review")
            result[key] = value
        return result
    def invalid_constant(value):
        raise ValueError("Nonfinite JSON value requires review")
    return json.loads(text, parse_float=Decimal, object_pairs_hook=pairs, parse_constant=invalid_constant)


def load_submission(run, case, stage):
    run = Path(run)
    final = run/case/stage/"final"
    status_file = run/"status.json"
    state = read(status_file).get("tasks", {}).get(case, {}).get(stage, "unknown") if status_file.exists() else "unknown"
    if not final.exists():
        if state not in TERMINAL_FAILURES:
            raise ValueError(f"Scoring deferred: {case}/{stage} is {state}; missing output is not a final failure")
        return None, {"execution_state": state, "availability": "terminal_no_output"}
    stamp = verify(final)  # A tampered archive is an integrity failure, never a model error.
    db = final/"database.json"
    try:
        value = strict_json(db.read_text())
    except (ValueError, UnicodeError):
        value = None
    provenance = {"execution_state": state, "final_identity": stamp, "database_sha256": sha(db), "availability": "submitted"}
    assessment_path = final/"output-assessment.json"
    assessment = read(assessment_path) if assessment_path.exists() else {}
    provenance["final_response_received"] = assessment.get("final_response_received") is True
    provenance["terminal"] = provenance["final_response_received"] or state in TERMINAL_FAILURES | {"completed"}
    # The runner may preserve parsed partial objects only in its raw answer.
    # An intact object followed by one surplus closing brace is also evaluable.
    # The immutable raw answer and its strict-format failure remain unchanged.
    raw = final/"raw-answer.txt"
    unresolved_structure = False
    if not isinstance(value, dict) and raw.exists():
        raw_text = raw.read_text()
        try:
            candidate, extraction = evaluable_json(raw_text)
        except (ValueError, UnicodeError) as error:
            candidate = None
            unresolved_structure = raw_text.lstrip().startswith(('{', '['))
            if unresolved_structure:
                provenance['extraction_error'] = str(error)
        if isinstance(candidate, dict):
            if set(candidate) in ({"database", "review"}, {"database", "annotations"}) and isinstance(candidate["database"], dict):
                candidate = candidate["database"]
            value = candidate
            provenance.update(availability="partial_from_exact_json", raw_sha256=sha(raw))
            if not extraction['strict_json_valid']:
                provenance.update(availability="recovered_complete_object", extraction=extraction)
    if not isinstance(value, dict):
        provenance["availability"] = ("terminal_no_usable_output" if provenance["terminal"]
            and not unresolved_structure else "unreadable_requires_review")
    return value, provenance

"""Published whole-field and complete-record counter."""
from collections import defaultdict
from .eligibility import exclusions
from .review_contract import EXPLICIT_NULL_STATES, pending_applicable

def _prediction_note(locator, cells, row, submitted):
    if not locator.startswith('/'):
        cell = cells.get(locator)
        return bool(cell and cell['row'] == row and cell['nonempty'])
    value = submitted
    try:
        for token in locator[1:].split('/'):
            token = token.replace('~1', '/').replace('~0', '~')
            if isinstance(value, list):
                if not token.isdecimal():
                    return False
                value = value[int(token)]
            else:
                value = value[token]
    except (KeyError, IndexError, TypeError):
        return False
    return isinstance(value, str) and bool(value.strip())


def _failed_state_rows(cells, mark, source_states, assessments, excluded_cells, excluded_rows, submitted):
    """Check status claims without changing the whole-field scoring inventory."""
    matched = {item["reference_row"]: item["prediction_row"] for item in mark["records"]
               if item["verdict"] == "matched" and item["reference_row"] not in excluded_rows}
    prediction = {(cell["row"], cell["field"]): cell for cell in cells.values()
                  if cell["side"] == "prediction"}
    expected = {}
    for source in source_states:
        cell = cells[source["reference_cell"]]
        row = matched.get(cell["row"])
        if (row is None or cell["id"] in excluded_cells or cell["nonempty"]
                or source["state"] not in EXPLICIT_NULL_STATES):
            continue
        candidate = prediction.get((row, cell["field"]))
        if candidate is None or not candidate["nonempty"]:
            expected[cell["id"]] = (source, row)

    if not isinstance(assessments, (list, tuple)):
        raise ValueError("Information-state assessments must be an array")
    seen, failed = set(), set()
    for assessment in assessments:
        if not isinstance(assessment, dict) or set(assessment) != {"reference_cell", "state", "locator"}:
            raise ValueError("Invalid information-state assessment")
        key = assessment["reference_cell"]
        if not isinstance(key, str) or key in seen or key not in expected:
            raise ValueError("Information-state assessment is duplicate or outside the applicable pair")
        source, row = expected[key]
        state, locator = assessment["state"], assessment["locator"]
        if isinstance(state, str) and state in EXPLICIT_NULL_STATES:
            if not isinstance(locator, str) or not _prediction_note(locator, cells, row, submitted):
                raise ValueError("Explicit information-state claims require a scoped prediction locator")
        elif state != "unspecified" or locator is not None:
            raise ValueError("Resolve applicable information-state assessments before scoring")
        seen.add(key)
        matches = state == source["state"] or (state == "unspecified" and not source["requires_explicit"])
        if not matches:
            failed.add(cells[key]["row"])
    if seen != set(expected):
        raise ValueError("Review all applicable double-empty information states before scoring")
    return failed


def projected(inv,mark,case,dispositions=(), *, source_states=(), state_assessments=(), submitted=None):
 """Project independent field and record eligibility, then count whole targets."""
 cs={r['id']:r for r in inv['cells']}
 _,_,ec,er=exclusions(inv,mark,case,dispositions)
 unresolved,_=pending_applicable(inv,mark,er,ec,set(),source_states)
 if unresolved:
  raise ValueError('Resolve applicable scientific uncertainty before final scoring')
 cats={i:m['category']for m in mark['cells']for i in[m.get('prediction_cell'),m.get('reference_cell')]if i}
 gold={c['id']for c in inv['cells']if c['side']=='reference'and c['nonempty']and cats[c['id']]=='scientific'and c['id']not in ec};pred={c['id']for c in inv['cells']if c['side']=='prediction'and c['nonempty']and cats[c['id']]=='scientific'and c['id']not in ec}
 tp=sum(m['verdict']=='correct'and m.get('prediction_cell')in pred and m.get('reference_cell')in gold for m in mark['cells']);gr=({r['id']for r in inv['rows']if r['side']=='reference'and r['declared_table']}|{cs[i]['row']for i in gold})-er;pr=({r['id']for r in inv['rows']if r['side']=='prediction'and r['declared_table']}|{cs[i]['row']for i in pred})-er
 by=defaultdict(list)
 for m in mark['cells']:
  for i in[m.get('prediction_cell'),m.get('reference_cell')]:
   if i:by[cs[i]['row']].append(m)
 failed_states=_failed_state_rows(cs,mark,source_states,state_assessments,ec,er,submitted) if source_states or state_assessments else set()
 complete=0
 for m in mark['records']:
  if m.get('reference_row')not in gr or m['reference_row'] in failed_states:continue
  mm=by[m['reference_row']]+by.get(m.get('prediction_row'),[]);complete+=m['verdict']=='matched'and all(x['verdict']in['correct','not_scored']for x in mm)
 def metrics(m,p,g):
  assert m<=min(p,g)
  return {'tp':m,'predicted':p,'gold':g,'precision':(m/p if p else 0)if g else None,'recall':m/g if g else None,'f1':2*m/(p+g)if g else None}
 return {'field':metrics(tp,len(pred),len(gold)),'record':metrics(complete,len(pr),len(gr))}

"""Offline replay of versioned, exhaustive judgments; never invokes a grader."""
import argparse
from collections import defaultdict
from copy import deepcopy
import csv
import gzip
import hashlib
import itertools
import json
from pathlib import Path
from model_conversation.archive import encoded, exact_json
from .task_grading_contract import inventory, mark_all

LEVELS = ('field', 'record')
METRICS = tuple(f'{level}_{name}' for level in LEVELS for name in ('precision','recall','f1'))
COUNTS = tuple(f'{level}_{name}' for level in LEVELS for name in ('tp','predicted','gold'))
SIGNATURE_VERSION = 'lossless-decimal-1'

def digest(value):
    return hashlib.sha256(encoded(value)).hexdigest()

def read(path, *, lossless=False):
    data=path.read_bytes()
    data=gzip.decompress(data) if path.suffix=='.gz' else data
    return exact_json(data) if lossless else json.loads(data)

def value_content(value_json):
    """Compare types and written decimal precision, not Decimal numeric equality."""
    return encoded(exact_json(value_json)).decode()

def diagnostic_content(diagnostics):
    return [{**d,'value_json':value_content(d['value_json'])} for d in diagnostics]

def bound_path(root, relative):
    p=Path(relative)
    if p.is_absolute() or '..' in p.parts or not p.parts:
        raise ValueError('Artifact path must be relative and contained in the bundle')
    target=(root/p).resolve()
    if not target.is_relative_to(root.resolve()):
        raise ValueError('Artifact symlink escapes the bundle')
    return target

def databases(inv):
    """Reconstruct submitted cells without inventing absent fields or repairing values."""
    result={'prediction':{},'reference':{}}
    by_row=defaultdict(list)
    for c in inv['cells']:by_row[c['row']].append(c)
    for r in inv['rows']:
        table=result[r['side']].setdefault(r['table'],[])
        while len(table)<=r['row_index']:table.append(None)
        if table[r['row_index']] is not None:raise ValueError('Duplicate inventory row location')
        table[r['row_index']]={c['field']:exact_json(c['value_json']) for c in by_row[r['id']] if c['present']}
    for d in inv['diagnostics']:
        value=exact_json(d['value_json'])
        if d['row_index'] is None:result['prediction'][d['table']]=value
        else:
            table=result['prediction'].setdefault(d['table'],[])
            while len(table)<=d['row_index']:table.append(None)
            table[d['row_index']]=value
    return result

def inventory_content(inv):
    """Pointer-independent integrity representation, retaining every declared role/state."""
    rows={r['id']:r for r in inv['rows']}
    if len(rows)!=len(inv['rows']) or len({c['id'] for c in inv['cells']})!=len(inv['cells']):
        raise ValueError('Duplicate inventory pointers')
    seen=set();values=[]
    for c in inv['cells']:
        r=rows.get(c['row'])
        if not r or any(c[k]!=r[k] for k in ('side','table','row_index')):
            raise ValueError('Invalid inventory cell/row binding')
        loc=(c['side'],c['table'],c['row_index'],c['field'])
        if loc in seen:raise ValueError('Duplicate inventory cell location')
        seen.add(loc)
        values.append([*loc,c['role'],c['present'],c['nonempty'],value_content(c['value_json'])])
    return {'rows':sorted((r['side'],r['table'],r['row_index'],r['declared_table']) for r in rows.values()),
            'cells':sorted(values,key=lambda x:tuple(x[:4])),'diagnostics':diagnostic_content(inv['diagnostics'])}

def context_signature(inv, spec):
    """Conservative whole-database identity, preserving linked object content.

    Three expansions cover the released schemas' dependency depth. Unresolved or
    ambiguous identifiers retain their literal target and multiplicity. Equality
    is a consistency check, not proof of scientific correctness.
    """
    rows={r['id']:r for r in inv['rows'] if r['side']=='prediction'}
    values={rid:{} for rid in rows}
    for c in inv['cells']:
        if c['row'] in rows and c['role'] in ('scientific','identifier','unclassified') and c['present']:
            values[c['row']][c['field']]=exact_json(c['value_json'])
    indices=defaultdict(list);own={};links={}
    for rid,r in rows.items():
        s=spec.get(r['table'],{});key=s.get('identifier');refs=s.get('references',{})
        if key in values[rid]:indices[(r['table'],digest(values[rid][key]))].append(rid)
        own[rid]=[r['table'],{k:v for k,v in values[rid].items() if k!=key and k not in refs}]
        links[rid]={k:(target,values[rid][k]) for k,target in refs.items() if k in values[rid]}
    hashes={rid:digest(v) for rid,v in own.items()}
    for _ in range(3):
        updated={}
        for rid in rows:
            resolved={}
            for field,(table,value) in links[rid].items():
                def target(v):
                    matches=indices[(table,digest(v))]
                    return hashes[matches[0]] if len(matches)==1 else ['unresolved',len(matches),v]
                resolved[field]=sorted((target(v) for v in value),key=digest) if isinstance(value,list) else target(value)
            updated[rid]=digest([own[rid],resolved])
        hashes=updated
    return digest([sorted(hashes.values()),diagnostic_content(inv['diagnostics'])])

def replay(manifest_path, corrections_path=None):
    path=Path(manifest_path).resolve();root=path.parent;m=read(path)
    if m.get('format')!='biotracebench-replay-1':raise ValueError('Unknown replay format')
    files=m['files']
    for name,wanted in files.items():
        if hashlib.sha256(bound_path(root,name).read_bytes()).hexdigest()!=wanted:
            raise ValueError('Artifact hash mismatch: '+name)
    reference_paths={c['reference'] for c in m['cases']}
    def artifact(name):
        if name not in files:raise ValueError('Unbound artifact: '+name)
        return read(bound_path(root,name),lossless=name in reference_paths)
    cases={c['case']:c for c in m['cases']}
    if len(cases)!=len(m['cases']):raise ValueError('Duplicate cases')
    if len(set(m['models']))!=len(m['models']) or len(set(m['conditions']))!=len(m['conditions']):
        raise ValueError('Duplicate model or condition')
    keys=[(p['model'],p['case'],p['condition']) for p in m['positions']]
    expected=set(itertools.product(m['models'],cases,m['conditions']))
    if len(set(keys))!=len(keys) or set(keys)!=expected:raise ValueError('Missing, duplicate or unknown positions')
    overlays=defaultdict(list)
    if corrections_path:
        corrections=read(Path(corrections_path))
        if corrections['baseline_manifest_sha256']!=hashlib.sha256(path.read_bytes()).hexdigest():
            raise ValueError('Corrections bind a different baseline manifest')
        for change in corrections['changes']:
            key=tuple(change['position'])
            if key not in expected:raise ValueError('Correction targets an unknown position')
            for e in change['evidence']:
                if files.get(e['path'])!=e['sha256']:raise ValueError('Correction evidence is not bound')
            if not change['evidence'] or not change['reason'].strip():raise ValueError('Correction lacks evidence/rationale')
            overlays[key].append(change)
    policy=artifact(m['policy']);scores=[];duplicates=defaultdict(list)
    for case,meta in cases.items():
        spec=artifact(meta['dictionary']);ref=artifact(meta['reference'])
        empty=inventory({},ref,spec,policy)
        gold={'field':sum(c['nonempty'] and c['role']=='scientific' for c in empty['cells']),
              'record':sum(r['declared_table'] for r in empty['rows'])}
        for pos in (p for p in m['positions'] if p['case']==case):
            key=(pos['model'],case,pos['condition']);zero=pos.get('zero_cause')
            if pos['domain']!=meta['domain']:raise ValueError('Position domain differs from case')
            row={k:pos[k] for k in ('model','case','condition','domain')};row['zero_cause']=zero
            if zero:
                if pos.get('judgment') or overlays[key]:raise ValueError('Zero position cannot carry an evaluable judgment/correction')
                row.update({k:0 for k in COUNTS+METRICS})
                row.update(field_gold=gold['field'],record_gold=gold['record'])
            else:
                bundle=artifact(pos['judgment']);inv=bundle['inventory'];marks=deepcopy(bundle['marking'])
                regenerated=inventory(databases(inv)['prediction'],ref,spec,policy)
                if inventory_content(inv)!=inventory_content(regenerated):raise ValueError('Archived inventory differs from bound submission/reference')
                targets=set()
                for change in overlays[key]:
                    if files[pos['judgment']]!=change['judgment_sha256']:raise ValueError('Correction judgment hash mismatch')
                    pair=(change['prediction_cell'],change['reference_cell'])
                    if pair in targets:raise ValueError('Duplicate correction target')
                    targets.add(pair)
                    matches=[v for v in marks['cells'] if (v['prediction_cell'],v['reference_cell'])==pair]
                    if len(matches)!=1 or matches[0]['verdict']!=change['old_verdict']:raise ValueError('Correction precondition mismatch')
                    if change['new_verdict'] not in ('correct','incorrect') or change['old_verdict'] not in ('correct','incorrect'):
                        raise ValueError('Cell overlay cannot change identity, role or presence')
                    matches[0].update(verdict=change['new_verdict'],reason=change['reason'])
                result=mark_all(inv,marks)
                if result['unresolved_items'] or any(result[l] is None for l in LEVELS):raise ValueError('Unresolved counts cannot be finalized')
                row.update({f'{l}_{n}':result[l][n] for l in LEVELS for n in ('tp','predicted','gold','precision','recall','f1')})
                if any(row[f'{l}_gold']!=gold[l] for l in LEVELS):raise ValueError('Reference denominator differs across positions')
                duplicates[(case,context_signature(inv,spec))].append(row)
            if not corrections_path and pos.get('expected'):
                if any(abs(row[k]-pos['expected'][k])>1e-12 for k in COUNTS+METRICS):raise ValueError('Replayed score differs from baseline: '+str(key))
            scores.append(row)
    conflicts=[];groups=0
    for (case,signature),group in duplicates.items():
        if len(group)>1:
            groups+=1
            if len({tuple(row[k] for k in COUNTS) for row in group})>1:
                conflicts.append({'case':case,'signature':signature,'positions':group})
    return {'scores':scores,'positions':len(scores),'zero_positions':sum(bool(r['zero_cause']) for r in scores),
            'identical_content_groups':groups,'consistency_conflicts':conflicts,
            'consistency_signature_version':SIGNATURE_VERSION,
            'baseline_manifest_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
            'corrections_sha256':hashlib.sha256(Path(corrections_path).read_bytes()).hexdigest() if corrections_path else None,
            'candidate':bool(corrections_path)}

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--manifest',required=True);p.add_argument('--out',required=True)
    p.add_argument('--corrections',help='Optional evidence-bound candidate overlay; never edits the baseline')
    a=p.parse_args(argv);result=replay(a.manifest,a.corrections)
    out=Path(a.out);out.mkdir(parents=True,exist_ok=False)
    (out/'replay.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    with (out/'scores.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,list(result['scores'][0]));w.writeheader();w.writerows(result['scores'])
    print(json.dumps({k:v for k,v in result.items() if k not in ('scores','consistency_conflicts')}))
    return 1 if result['consistency_conflicts'] else 0

if __name__=='__main__':raise SystemExit(main())

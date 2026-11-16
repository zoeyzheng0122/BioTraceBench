"""Independent count and cohort checks at the paper-analysis boundary.

Analysis consumes archived decisions as data; it does not invoke a grader or
import the scoring package. This counter checks the replay interchange file.
"""
from collections import defaultdict
from copy import deepcopy
from itertools import product
import math

LEVELS=('field','record')
COUNTS=tuple(f'{l}_{q}' for l in LEVELS for q in ('tp','predicted','gold'))

def reference_counts(reference, dictionary, policy):
    """Independently count bound references, including studies with no judgments."""
    if policy.get('reference_contract')!='biotracebench-fixed-reference-1' or policy.get('compound_fields'):
        raise ValueError('Analysis requires the fixed-reference whole-field contract')
    if not isinstance(reference,dict):raise ValueError('Reference must be a readable database')
    fields=records=0
    for table in sorted(set(dictionary)|set(reference)):
        rows=reference.get(table,[])
        if not isinstance(rows,list):raise ValueError('Reference tables must be arrays')
        spec=dictionary.get(table,{'fields':[]})
        known={f['key'] for f in spec['fields']}
        for row in rows:
            if not isinstance(row,dict):raise ValueError('Reference rows must be readable records')
            if not known.issubset(row):raise ValueError('Reference is missing a declared field')
            records+=table in dictionary
            for key,value in row.items():
                primary=key==spec.get('identifier')
                role=policy.get('field_roles',{}).get(table+'.'+key) or (
                    'identifier' if primary else 'scientific' if key in known else 'unclassified')
                if (role not in {'identifier','scientific','provenance','unclassified'} or
                        primary!=(role=='identifier') or key in spec.get('references',{}) and role!='scientific'):
                    raise ValueError('Invalid reference field role: '+table+'.'+key)
                if role=='scientific' and not (value is None or isinstance(value,str) and not value.strip()):fields+=1
    return fields,records

def count(bundle):
    inv=bundle['inventory'];marks=bundle['marking'];cells={c['id']:c for c in inv['cells']}
    included={r['id']:r['side'] for r in inv['rows'] if r['declared_table']}
    predicted=set();gold=set();matched=set();active=set();incomplete=set()
    for m in marks['cells']:
        p,g=(cells.get(m[k]) for k in ('prediction_cell','reference_cell'))
        linked={c['row'] for c in (p,g) if c}
        if m['verdict'] not in ('correct','not_scored'):incomplete.update(linked)
        if m['category']!='scientific':continue
        for c,items in ((p,predicted),(g,gold)):
            if c and c['nonempty']:
                items.add(c['id']);included[c['row']]=c['side'];active.update(linked)
        if m['verdict']=='correct':matched.add((p['id'],g['id']))
    records=sum(r['verdict']=='matched' and r['reference_row'] in active and
                r['reference_row'] not in incomplete and r['prediction_row'] not in incomplete
                for r in marks['records'])
    return {'field_tp':len(matched),'field_predicted':len(predicted),'field_gold':len(gold),
            'record_tp':records,'record_predicted':sum(v=='prediction' for v in included.values())+sum(d['counted_record'] for d in inv['diagnostics']),
            'record_gold':sum(v=='reference' for v in included.values())}

def validate_replay(replayed, manifest, artifact, corrections=None, corrections_sha256=None):
    positions={(p['model'],p['case'],p['condition']):p for p in manifest['positions']}
    cases={c['case']:c for c in manifest['cases']}
    grid=set(product(manifest['models'],cases,manifest['conditions']))
    rows=replayed['scores'];keys=[(r['model'],r['case'],r['condition']) for r in rows]
    if len(positions)!=len(manifest['positions']) or set(positions)!=grid or len(set(keys))!=len(keys) or set(keys)!=grid:
        raise ValueError('Analysis replay grid differs from the bound manifest')
    overlays=defaultdict(list)
    if replayed['candidate']:
        if (not corrections or not corrections_sha256 or replayed.get('corrections_sha256')!=corrections_sha256 or
                corrections['baseline_manifest_sha256']!=replayed['baseline_manifest_sha256']):
            raise ValueError('Candidate analysis requires the actual bound overlay')
        for change in corrections['changes']:
            key=tuple(change['position'])
            if key not in grid:raise ValueError('Candidate overlay targets an unknown position')
            if not change['evidence'] or not change['reason'].strip():raise ValueError('Overlay lacks evidence or rationale')
            if any(manifest['files'].get(e['path'])!=e['sha256'] for e in change['evidence']):raise ValueError('Overlay evidence differs from the bound manifest')
            overlays[key].append(change)
    elif corrections or replayed.get('corrections_sha256'):
        raise ValueError('Baseline analysis cannot carry a candidate overlay')
    policy=artifact(manifest['policy'])
    denominators={case:reference_counts(artifact(meta['reference']),artifact(meta['dictionary']),policy)
                  for case,meta in cases.items()}
    wanted={}
    for key,p in positions.items():
        if p.get('zero_cause'):
            if overlays[key]:raise ValueError('Candidate overlay targets a zero position')
            continue
        bundle=deepcopy(artifact(p['judgment']));seen=set()
        for change in overlays[key]:
            if change['judgment_sha256']!=manifest['files'][p['judgment']]:raise ValueError('Overlay judgment hash mismatch')
            pair=(change['prediction_cell'],change['reference_cell'])
            if pair in seen:raise ValueError('Duplicate overlay cell')
            seen.add(pair)
            matches=[m for m in bundle['marking']['cells'] if (m['prediction_cell'],m['reference_cell'])==pair]
            if len(matches)!=1 or matches[0]['verdict']!=change['old_verdict']:raise ValueError('Overlay old verdict mismatch')
            if change['new_verdict'] not in ('correct','incorrect') or change['old_verdict'] not in ('correct','incorrect'):raise ValueError('Unsupported overlay verdict')
            matches[0]['verdict']=change['new_verdict']
        wanted[key]=count(bundle)
        if (wanted[key]['field_gold'],wanted[key]['record_gold'])!=denominators[p['case']]:
            raise ValueError('Judgment reference counts differ from the bound reference: '+str(key))
    for row,key in zip(rows,keys):
        p=positions[key];zero=p.get('zero_cause')
        if row['domain']!=cases[p['case']]['domain'] or p['domain']!=row['domain'] or row.get('zero_cause')!=zero:
            raise ValueError('Analysis domain or zero classification differs from the manifest')
        if zero:
            gold_field,gold_record=denominators[p['case']]
            wanted[key]={q:0 for q in COUNTS};wanted[key].update(field_gold=gold_field,record_gold=gold_record)
        for q in COUNTS:
            if isinstance(row[q],bool) or not isinstance(row[q],(int,float)) or not math.isfinite(row[q]) or row[q]!=wanted[key][q]:
                raise ValueError('Replay count differs from archived item judgments: '+str(key)+' '+q)
        for level in LEVELS:
            t,n,g=(row[f'{level}_{q}'] for q in ('tp','predicted','gold'))
            if not (0<=t<=min(n,g)):raise ValueError('Invalid count range')
            values=(0,0,0) if zero else (t/n if n else int(not g),t/g if g else int(not n),2*t/(n+g) if n+g else 1)
            for q,v in zip(('precision','recall','f1'),values):
                actual=row[f'{level}_{q}']
                if isinstance(actual,bool) or not isinstance(actual,(int,float)) or not math.isfinite(actual) or abs(actual-v)>1e-12:
                    raise ValueError('Replay metric differs from its verified counts: '+str(key)+' '+level+'_'+q)

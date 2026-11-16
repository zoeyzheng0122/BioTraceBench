"""Replay only initial-output positions, retaining native verification rules."""
from pathlib import Path

from model_conversation.archive import digest, sha
from . import native_codex as native
from . import native_adjudication as adjudication


def export_i0(plan, out, *, adjudications=None):
    """Export the final reviewed/source-adjudicated I0 view without other stages."""
    root, out = Path(plan), Path(out)
    with native._lock(root):
        routes = native._json(root/'private/routes.json')
        selected = [r for r in routes if r['condition'] == 'i0']
        if not selected:
            raise ValueError('Native plan has no initial-output positions')
        jobs = sorted({r['job_id'] for r in selected})
        frozen = native._verify_plan(root, jobs)
        if (digest(routes) != frozen['routes_identity'] or len(routes) != frozen['positions'] or
                {r['job_id'] for r in routes} != set(frozen['jobs'])):
            raise ValueError('Native route coverage or identity changed')
        keys = [(r['case'],r['model'],r['condition']) for r in selected]
        if len(keys) != len(set(keys)):
            raise ValueError('Duplicate initial-output position')
        if adjudications is not None:
            unknown = {p.name for p in (Path(adjudications)/'adjudications').glob('*') if p.is_dir()} - set(frozen['jobs'])
            if unknown:
                raise ValueError('Unknown native job in source adjudications')
        source_files = {root/'plan.json',root/'private/routes.json',Path(__file__),
                        Path(native.__file__),Path(adjudication.__file__),
                        root/'judge-inputs/instruction.json'}
        for name,expected in frozen['implementation'].items():
            path=(Path(native.__file__).parent.parent/name if name.startswith('model_conversation/')
                  else Path(native.__file__).parent/name)
            if sha(path)!=expected:
                raise ValueError('Native implementation identity changed')
            source_files.add(path)
        if adjudications is not None:
            source_files.add(Path(adjudication.__file__).with_name('native_consistency.py'))
        results = {}
        for job in jobs:
            packet, context = native._inputs(root,job,frozen)
            attempts = native._recheck_attempts(root,job,packet,context,frozen)
            first = native._valid_complete(attempts,'first')
            review = native._valid_complete(attempts,'review')
            chosen, score, selection, base_score = None, None, None, None
            if packet['local_terminal']:
                if attempts:
                    raise ValueError('Local terminal job contains native imports')
                score = native._score(packet['inventory'],native._local_reply(packet['inventory'],context['task_policy']),context['task_policy'])
                status = 'complete' if native._score_complete(score) else 'local_zero_unresolved'
            elif review or first and not frozen['require_review']:
                chosen = (review or first)[-1];score = chosen['score']
                status = 'complete' if native._score_complete(score) else 'unresolved'
            elif first:
                status = ('review_validation_error' if attempts[-1]['phase']=='review' and
                          attempts[-1]['status']=='validation_error' else 'awaiting_review')
            elif attempts and attempts[-1]['status']=='validation_error':
                status = 'validation_error'
            elif native._mapping_for(attempts,'first') is not None:
                status = 'awaiting_fields'
            else:
                status = 'awaiting_first_pass'
            if adjudications is not None and not packet['local_terminal'] and (Path(adjudications)/'adjudications'/job).exists():
                _,_,_,base,_,history = adjudication._history(root,job,adjudications)
                if history:
                    item=history[-1][1];base_score=score;score=item['score'];status='complete'
                    selection={'phase':'source_adjudication','identity':item['identity'],
                               'base_import_identity':base['identity']}
                    source_files.update(path for path,_ in history)
            packet_path=(root/'judge-inputs/jobs'/job/'packet.json').resolve()
            context_path=(root/'judge-inputs/tasks'/packet['task_id']/'context.json').resolve()
            source_files.update((packet_path,context_path))
            source_files.update((root/'imports'/job).glob('*.json'))
            source_files.update(Path(a['path']) for a in context.get('source_artifacts',[]))
            result={'job_id':job,'input_identity':packet['input_identity'],'packet_path':str(packet_path),
                    'status':status,'score':score if status=='complete' else None,
                    'selected_judgment':selection,'base_score':base_score,
                    'first_pass_identity':first[-1]['identity'] if first else None,
                    'review_identity':review[-1]['identity'] if review else None}
            results[job]=result
        snapshot=digest({'plan':frozen['identity'],'condition':'i0','jobs':results})
        snapshot_root=out/'snapshots'/snapshot
        for job,result in results.items():
            path=snapshot_root/'jobs'/job/'result.json';native._write_once(path,result);source_files.add(path)
        positions=[]
        for route in selected:
            result=results[route['job_id']];score=result['score'];complete=result['status']=='complete'
            row={'identity':{k:route[k] for k in ('case','model','condition','domain')},
                 'status':result['status'],'score':{k:score[k] for k in ('field','record')} if complete else None,
                 'field_items':[[i['table'],i['row_index'],i['field'],i['correct']]
                                for i in score['field_items'] if i['gold']] if complete else [],
                 'record_items':[[i['table'],i['row_index'],i['correct']]
                                 for i in score['record_items'] if i['reference_row'] and i.get('applicable',True)] if complete else [],
                 'packet_path':result['packet_path'],'result_path':str((snapshot_root/'jobs'/route['job_id']/'result.json').resolve()),
                 'input_identity':result['input_identity']}
            if result['selected_judgment']:row['selected_judgment']=result['selected_judgment']
            if result['base_score'] is not None:
                row['base_score']={k:result['base_score'][k] for k in ('field','record')}
            positions.append(row)
        data={'format':'biotracebench-native-comparison-input-2','validation_status':'exact_replay_passed',
              'protocol':native.PROTOCOL,'positions':positions,'historical':[],'audit':[],
              'audit_provenance':{},'judgment_view':'source_adjudicated' if adjudications is not None else 'reviewed',
              'source_sha256':{str(path.resolve()):sha(path) for path in source_files}}
        output=out/'exports'/digest(data)/'comparison-input.json';native._write_once(output,data)
        return {'path':str(output.resolve()),'sha256':sha(output),'positions':len(positions),
                'judgment_view':data['judgment_view'],'validation_status':data['validation_status']}

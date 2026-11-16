"""Standalone correction reports for external manual inspection, with no approval gate."""
import csv
import html
import io
import json
import os
from pathlib import Path
from model_conversation.archive import write

# Completion describes this submitted generation run only. It never waits for
# other generation models or a later analysis report.
WORKFLOW_SCOPE = {'input_scope':'single_generation_run',
                  'other_model_results_required':False,
                  'cross_model_aggregation':'outside_scoring',
                  'score_comparison':'outside_scoring',
                  'analysis_required_for_completion':False}


def _text(value):
    return html.escape(str(value))


def _csv(value):
    value = '' if value is None else str(value)
    return "'"+value if value.startswith(('=','+','-','@')) else value


def _atomic_text(path, text, encoding='utf-8'):
    temp=path.with_name(path.name+'.tmp')
    with temp.open('w',encoding=encoding,newline='') as stream:
        stream.write(text)
        stream.flush()
        os.fsync(stream.fileno())
    temp.replace(path)


def task_report(folder, entry, result=None, protocol_bundle=None):
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
    title=entry['case_id']+' / '+entry['condition']
    details=[];csv_rows=[]
    if result:
        for item in result['cells']:
            p,g=item['prediction'],item['reference'];cell=p or g
            row={'table':cell['table'],'prediction_row':p['row_index']+1 if p else '',
                 'reference_row':g['row_index']+1 if g else '', 'field':cell['field'],
                 'prediction_present':p['present'] if p else False,
                 'reference_present':g['present'] if g else False,
                 'prediction':p['value_json'] if p and p['present'] else '(absent)',
                 'reference':g['value_json'] if g and g['present'] else '(absent)',
                 'category':item['category'],'verdict':item['verdict'],'reason':item['reason']}
            csv_rows.append(row)
            details.append('<tr>'+''.join('<td>'+_text(row[k])+'</td>' for k in
                ('table','prediction_row','reference_row','field','prediction','reference','verdict','reason'))+'</tr>')
    fields=['table','prediction_row','reference_row','field','prediction_present','reference_present',
            'prediction','reference','category','verdict','reason']
    stream=io.StringIO(newline='')
    writer=csv.DictWriter(stream,fieldnames=fields);writer.writeheader()
    writer.writerows({k:_csv(v) for k,v in row.items()} for row in csv_rows)
    summary={k:result.get(k) for k in ('field','record','score_basis','mark_counts','uncertainty','reference_issues')} if result else entry
    page='<!doctype html><meta charset="utf-8"><title>'+_text(title)+'</title>'
    page+='<style>body{font:15px system-ui;margin:2rem}table{border-collapse:collapse;width:100%}td,th{border:1px solid #ddd;padding:.5rem;vertical-align:top;white-space:pre-wrap;overflow-wrap:anywhere}pre{white-space:pre-wrap}</style>'
    page+='<h1>'+_text(title)+'</h1><p>Status: '+_text(entry['status'])+'</p><pre>'+_text(json.dumps(summary,ensure_ascii=False,indent=2))+'</pre>'
    if entry.get('archive_integrity'):
        page+='<h2>Archive provenance</h2><pre>'+_text(json.dumps(entry['archive_integrity'],ensure_ascii=False,indent=2))+'</pre>'
    if result:
        if result.get('precision_policy'):
            page+='<h2>Numeric precision</h2><pre>'+_text(json.dumps(result['precision_policy'],ensure_ascii=False,indent=2))+'</pre>'
        if result['score_basis']=='lower_bound_unresolved':
            page+='<p>Unresolved judgments await manual review. Scores are provisional lower bounds.</p>'
        elif result['score_basis']=='undefined_classification':
            page+='<p>Some denominators require review; affected metrics are undefined.</p>'
        page+='<h2>Record alignment</h2><pre>'+_text(json.dumps(result['records'],ensure_ascii=False,indent=2))+'</pre>'
        if result.get('alignment_protocol'):
            page+='<h2>EFE identity evidence</h2><pre>'+_text(json.dumps({
                'protocol':result['alignment_protocol'],'binding':result.get('alignment_binding'),
                'validation':result.get('alignment_evidence_validation'),
                'records':result.get('alignment_audit',[])},ensure_ascii=False,indent=2))+'</pre>'
    diagnostics=result.get('structural_diagnostics',[]) if result else entry.get('structural_diagnostics',[])
    pending=result.get('review_items',[]) if result else []
    if diagnostics:
        page+='<h2>Structural issues</h2><pre>'+_text(json.dumps(diagnostics,ensure_ascii=False,indent=2))+'</pre>'
    if (folder/'raw-grading.txt').exists():
        page+='<details><summary>Original judge response</summary><pre>'+_text((folder/'raw-grading.txt').read_text())+'</pre></details>'
    page+='<h2>Cell judgments</h2><table><thead><tr>'+''.join('<th>'+x+'</th>' for x in
        ('Table','Prediction row','Reference row','Field','Prediction','Reference','Verdict','Reason'))+'</tr></thead><tbody>'+''.join(details)+'</tbody></table>'
    # Finish rendering before replacing any existing published report file.
    write(folder/'marking.json',{'entry':entry,'result':result})
    write(folder/'structural-issues.json',diagnostics)
    write(folder/'pending-review.json',pending)
    if protocol_bundle is not None:
        write(folder/'protocol-bundle.json',protocol_bundle)
    _atomic_text(folder/'cells.csv',stream.getvalue(),encoding='utf-8-sig')
    _atomic_text(folder/'review.html',page)


def overview(folder, entries, results, policy_frozen):
    folder=Path(folder)
    from model_conversation.archive import read
    scope=read(folder/'scoring-scope.json') if (folder/'scoring-scope.json').exists() else None
    finished=sum(e['status']=='automatic_scoring_completed' for e in entries)
    waiting=sum(e['status']=='waiting_for_input' for e in entries)
    pending=sum(e['status']=='prepared' for e in entries)
    failed=len(entries)-finished-waiting-pending
    conflicts=sum(e.get('archive_integrity',{}).get('status')=='conflict' for e in entries)
    state=('paused' if pending else 'waiting_for_inputs' if waiting else
           'automatic_scoring_completed_with_errors' if failed or conflicts else 'automatic_scoring_completed')
    summary={'status':state,'expected_outputs':len(entries),'graded_outputs':finished,
             'failed_outputs':failed,'waiting_outputs':waiting,'not_started_outputs':pending,
             'automatic_workflow_finished':state in {'automatic_scoring_completed','automatic_scoring_completed_with_errors'},
             'all_selected_outputs_graded':bool(entries) and finished==len(entries),
             'archive_conflicts':conflicts,
             'policy_frozen':policy_frozen,'human_review':{'status':'external_not_recorded',
             'required_for_automatic_completion':False},'outputs':entries}
    summary['workflow_scope']=dict(WORKFLOW_SCOPE)
    summary['uncertainty']={k:sum(r.get('uncertainty',{}).get(k,0) for r in results.values())
                            for k in ('fields','records','structural_issues')}
    summary['uncertainty']['affected_outputs']=sum(bool(r.get('review_items')) for r in results.values())
    preparation=folder/'preparation-status.json'
    if preparation.exists():
        summary['preparation']=read(preparation)
        if not summary['preparation']['can_start_grading']:
            summary.update(status=summary['preparation']['status'],model_calls=0,
                           automatic_workflow_finished=False)
    if scope:
        summary['scoring_scope']=scope
        summary['all_experiment_conditions_selected']=scope['selected_conditions']==scope['expected_conditions']
    write(folder/'status.json',summary)
    studies={}
    for entry in entries:
        result=results.get(entry['id'])
        study=studies.setdefault(entry['case_id'],{'case_id':entry['case_id'],
             'study_id':entry.get('study_id',entry['case_id']),'domain':entry.get('domain'),
             'conditions':{},'outputs':{}})
        if scope:study['scoring_scope']=scope
        study['outputs'][entry['condition']]=entry['status']
        if result:
            study['conditions'][entry['condition']]={**result,'automatic_scoring_status':result['status'],
                'status':'provisional'}  # Analysis must not mislabel unaudited machine marks as human-approved final scores.
    write(folder/'study-scores.json',list(studies.values()))
    links=[]
    for entry in entries:
        target='tasks/'+entry['id']+'/review.html'
        links.append('<li><a href="'+target+'">'+_text(entry['case_id']+' / '+entry['condition'])+
                     '</a> — '+_text(entry['status'])+'; archive: '+
                     _text(entry.get('archive_integrity',{}).get('status','not_observed'))+'</li>')
    _atomic_text(folder/'review.html','<!doctype html><meta charset="utf-8"><title>Task grading</title>'
        '<h1>Task grading</h1><p>Open each task report to review judgments and unresolved items.</p>'
        '<pre>'+_text(json.dumps({k:v for k,v in summary.items() if k!='outputs'},ensure_ascii=False,indent=2))+
        '</pre><ul>'+''.join(links)+'</ul>')
    return summary

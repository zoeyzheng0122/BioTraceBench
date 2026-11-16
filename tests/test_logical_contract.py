"""Synthetic native judgments: validate bindings/counts, not model accuracy.

All scientific verdicts and correspondences below are explicit fixture inputs.
The counting implementation never infers biomedical equivalence from strings.
No study sources, real case labels, historical scores or provider calls occur.
"""
import copy
import json
import unittest

from biotracebench_scoring import logical_contract as lc
from biotracebench_scoring.task_grading_contract import inventory


PHYSICAL_POLICY = {'reference_contract': 'biotracebench-fixed-reference-1', 'field_roles': {}}


def packet(prediction, reference, fields):
    dictionary = {table: {'identifier': 'id', 'fields': [{'key': k} for k in ('id', *keys)]}
                  for table, keys in fields.items()}
    return inventory(prediction, reference, dictionary, PHYSICAL_POLICY)


def row(inv, side, table, index=0):
    return next(r['id'] for r in inv['rows']
                if (r['side'], r['table'], r['row_index']) == (side, table, index))


def cell(inv, side, table, field, index=0):
    return next(c for c in inv['cells']
                if (c['side'], c['table'], c['row_index'], c['field']) == (side, table, index, field))


def evidence(inv, side, table, field, index=0, quote=None, path=''):
    c = cell(inv, side, table, field, index)
    v = json.loads(c['value_json'])
    return {'cell': c['id'], 'path': path,
            'quote': quote if quote is not None else v if isinstance(v, str) else None}


def policy(inv):
    """Author literal fixture obligations; production scaffold leaves these blank."""
    value = lc.scaffold_policy(inv)
    for field in value['fields']:
        for assertion in field['required_assertions']:
            assertion.update(text='Recover the synthetic ' + field['field'] + ' fact.',
                             placement='strict', basis='Explicit synthetic task field placement.')
    return lc.bind_policy(value, inv)


def field_policy(value, table, field, index=0):
    return next(f for f in value['fields'] if f['id'] == f'{table}:{index}:{field}')


def mark(reply, table, field, index=0):
    return next(f for f in reply['fields'] if f['field_id'] == f'{table}:{index}:{field}')


def reply(inv, value, pairs=None):
    """Literal fixture correspondences are fixed independently of field verdicts."""
    if pairs is None:
        pairs = [(r['id'], row(inv, 'reference', r['table'], r['row_index']))
                 for r in inv['rows'] if r['side'] == 'prediction']
        used = {g for _, g in pairs}
        pairs += [(None, r['id']) for r in inv['rows'] if r['side'] == 'reference' and r['id'] not in used]
    records = [{'prediction_row': p, 'reference_row': g,
                'verdict': 'matched' if p and g else 'extra' if p else 'missing',
                'reason': 'Fixture declares this scientific object correspondence.'} for p, g in pairs]
    mapping = {g: p for p, g in pairs if g}
    result = {'records': records, 'fields': [], 'unscored': [], 'reference_issues': []}
    for f in value['fields']:
        p = mapping[f['reference_row']]
        pc = next((c for c in inv['cells'] if c['row'] == p and c['field'] == f['field']), None)
        ev = []
        if pc and pc['nonempty']:
            v = json.loads(pc['value_json'])
            ev = [{'cell': pc['id'], 'path': '', 'quote': v if isinstance(v, str) else None}]
        assertions = [{'assertion_id': a['id'], 'verdict': 'correct' if ev else 'missing',
                       'evidence': copy.deepcopy(ev),
                       'reason': 'Fixture judges the required fact equivalent.' if ev else 'No submitted expression.'}
                      for a in f['required_assertions']]
        result['fields'].append({'field_id': f['id'], 'prediction_evidence': ev,
                                 'assertions': assertions,
                                 'integrity': {'verdict': 'correct', 'evidence': [],
                                               'reason': 'Fixture judges no erroneous added assertion.'},
                                 'verdict': ('correct' if ev else 'missing') if assertions else ('extra' if ev else 'not_scored'),
                                 'reason': 'Explicit fixture whole-field judgment.'})
    return result


def move_expression(target, ev, correct=True):
    target['prediction_evidence'] = [copy.deepcopy(ev)]
    for assertion in target['assertions']:
        assertion.update(verdict='correct' if correct else 'incorrect', evidence=[copy.deepcopy(ev)],
                         reason='Native fixture judges this expressed assertion ' + ('equivalent.' if correct else 'wrong.'))
    target['verdict'] = 'correct' if correct else 'incorrect'


def link(inv, side, from_table, to_table, from_field, from_index=0, to_index=0, path=''):
    return {'id': f'{side}-{from_table}{from_index}-{to_table}{to_index}',
            'from_row': row(inv, side, from_table, from_index),
            'to_row': row(inv, side, to_table, to_index),
            'from_evidence': evidence(inv, side, from_table, from_field, from_index, path=path),
            'to_evidence': evidence(inv, side, to_table, 'id', to_index),
            'kind': 'identifier', 'reason': 'The submitted identifier explicitly links these objects.'}


class LogicalContractTests(unittest.TestCase):
    def test_version_is_opt_in_and_scaffold_requires_native_authorship(self):
        inv = packet({'sample': [{'id': 'p', 'name': 'A'}]},
                     {'sample': [{'id': 'g', 'name': 'A'}]}, {'sample': ['name']})
        self.assertEqual(lc.definition()['contract'], lc.CONTRACT)
        self.assertIn('native judge', lc.instruction())
        with self.assertRaises(ValueError):
            lc.bind_policy(lc.scaffold_policy(inv), inv)
        changed = policy(inv); changed['contract'] = 'unversioned'
        with self.assertRaises(ValueError): lc.validate_policy(changed, inv)

    def test_stable_template_rebinds_after_prediction_inventory_size_changes(self):
        reference = {'sample': [{'id': 'g', 'name': 'A'}]}
        a = packet({'sample': [{'id': 'p', 'name': 'A'}]}, reference, {'sample': ['name']})
        b = packet({'sample': [{'id': 'p', 'name': 'A'}, {'id': 'dup', 'name': 'A'}]}, reference, {'sample': ['name']})
        template = lc.policy_template(policy(a), a)
        bound = lc.bind_policy(template, b)
        self.assertNotEqual(policy(a)['fields'][0]['reference_row'], bound['fields'][0]['reference_row'])
        self.assertEqual(lc.policy_template(bound, b), template)
        result = lc.score(b, bound, reply(b, bound, [
            (row(b, 'prediction', 'sample', 0), row(b, 'reference', 'sample')),
            (row(b, 'prediction', 'sample', 1), None)]))
        self.assertEqual(result['known_field_counts'], {'tp': 1, 'predicted': 2, 'gold': 1})
        self.assertEqual(result['record']['tp'], 1)

    def test_same_object_control_state_in_other_field_is_logically_present(self):
        inv = packet({'sample': [{'id': 'p', 'model': None, 'source': 'C2C12 negative control'}]},
                     {'sample': [{'id': 'g', 'model': 'negative control', 'source': 'C2C12'}]},
                     {'sample': ['model', 'source']})
        pol = policy(inv)
        field_policy(pol, 'sample', 'model')['required_assertions'][0].update(
            placement='flexible', basis='The synthetic task asks for control identity without a field restriction.')
        ans = reply(inv, pol)
        move_expression(mark(ans, 'sample', 'model'), evidence(inv, 'prediction', 'sample', 'source', quote='negative control'))
        result = lc.score(inv, pol, ans)
        self.assertEqual(result['known_field_counts'], {'tp': 2, 'predicted': 2, 'gold': 2})
        self.assertEqual(result['physical']['field']['predicted'], 1)
        self.assertEqual(result['field_items'][0]['prediction_field_state'], 'null')

    def test_explicit_strict_placement_cannot_be_filled_from_other_field(self):
        inv = packet({'result': [{'id': 'p', 'value': None, 'notes': '5 ng/mL'}]},
                     {'result': [{'id': 'g', 'value': '5', 'notes': None}]},
                     {'result': ['value', 'notes']})
        pol = policy(inv); ans = reply(inv, pol)
        ev = evidence(inv, 'prediction', 'result', 'notes')
        move_expression(mark(ans, 'result', 'value'), ev)
        # The notes expression already serves the requested value; no second item.
        mark(ans, 'result', 'notes').update(prediction_evidence=[], verdict='not_scored')
        with self.assertRaisesRegex(ValueError, 'placement'): lc.score(inv, pol, ans)
        move_expression(mark(ans, 'result', 'value'), ev, correct=False)
        self.assertEqual(lc.score(inv, pol, ans)['known_field_counts'], {'tp': 0, 'predicted': 1, 'gold': 1})

    def test_task_permitted_count_proportion_layout_keeps_actual_companion_required(self):
        gold={'result':[{'id':'R','value':6,'unit':'participants','kind':'count',
                         'supplement':'60%; denominator 10'}]}
        pred={'result':[{'id':'P','value':60,'unit':'%','kind':'proportion',
                         'supplement':'Reported count 6 of 10 participants'}]}
        inv=packet(pred,gold,{'result':['value','unit','kind','supplement']})
        pol=policy(inv)
        duties={
            'value':'Use either explicitly reported count6 or proportion60 as the task-permitted principal.',
            'unit':'Use the unit of the task-permitted chosen principal, not the reference layout.',
            'kind':'Identify the task-permitted chosen principal as count or proportion.',
            'supplement':'Express the actual reported companion and denominator: count6of10 when proportion is principal.'}
        for f in pol['fields']:
            for a in f['required_assertions']:
                a.update(text=duties[f['field']],basis='Synthetic task explicitly permits either coupled-report layout.')
        ans=reply(inv,pol)
        score=lc.score(inv,pol,ans)
        self.assertEqual(score['known_field_counts'],{'tp':4,'predicted':4,'gold':4})
        self.assertEqual(score['record']['tp'],1)
        # Native fixture now finds the count absent. Source text cannot add it.
        incomplete=copy.deepcopy(pred);incomplete['result'][0]['supplement']='Denominator 10'
        inv=packet(incomplete,gold,{'result':['value','unit','kind','supplement']})
        ans=reply(inv,pol);companion=mark(ans,'result','supplement')
        companion['assertions'][0].update(verdict='missing',evidence=[],
            reason='The actual count is absent; deriving it from60percent and10is prohibited.')
        companion.update(verdict='incorrect',reason='Present denominator does not supply the required reported count.')
        score=lc.score(inv,pol,ans)
        self.assertEqual(score['known_field_counts'],{'tp':3,'predicted':4,'gold':4})
        self.assertEqual(score['record']['tp'],0)

    def _linked_rna(self):
        gold = {'sample': [{'id': 'S', 'material': 'RNA extracted with kit R'}],
                'assay': [{'id': 'A', 'sample_id': 'S', 'method': 'RNA extracted with kit R'}]}
        pred = copy.deepcopy(gold); pred['assay'][0]['method'] = None
        inv = packet(pred, gold, {'sample': ['material'], 'assay': ['sample_id', 'method']})
        pol = policy(inv)
        field_policy(pol, 'assay', 'method')['required_assertions'][0].update(
            placement='flexible', scope='linked', allowed_evidence=[{'table': 'sample', 'field': 'material'}],
            basis='Extraction belongs to the explicitly associated sample preparation.')
        ans = reply(inv, pol); ans['links'] = [link(inv, 'prediction', 'assay', 'sample', 'sample_id')]
        move_expression(mark(ans, 'assay', 'method'), evidence(inv, 'prediction', 'sample', 'material'))
        return inv, pol, ans

    def test_strict_time_requires_its_anchor_without_repeating_duration_quantity(self):
        gold={'condition':[{'id':'C','duration':3,'unit':'days','factor':'Differentiation duration',
                            'time':'3 days from differentiation start to RNA collection'}]}
        pred=copy.deepcopy(gold);pred['condition'][0]['time']='From differentiation start to RNA collection'
        fields={'condition':['duration','unit','factor','time']}
        inv=packet(pred,gold,fields);pol=policy(inv)
        field_policy(pol,'condition','time')['required_assertions'][0].update(
            text='Name the actual interval anchor/phase here; numeric extent belongs to duration/unit.',
            basis='The synthetic task separately assigns quantity and temporal-anchor duties.')
        ans=reply(inv,pol)
        self.assertEqual(lc.score(inv,pol,ans)['field']['tp'],4)
        pred['condition'][0].update(time='3 days',factor='Differentiation from start to RNA collection')
        inv=packet(pred,gold,fields);ans=reply(inv,pol)
        time=mark(ans,'condition','time')
        time['assertions'][0].update(verdict='missing',evidence=[],reason='Own time lacks its required event anchor.')
        time.update(verdict='incorrect',reason='Duration is expressed but the actual time anchor is omitted.')
        self.assertEqual(lc.score(inv,pol,ans)['known_field_counts'],{'tp':3,'predicted':4,'gold':4})
        move_expression(time,evidence(inv,'prediction','condition','factor'))
        with self.assertRaisesRegex(ValueError,'placement'):lc.score(inv,pol,ans)

    def test_linked_preparation_fact_uses_real_relationship_path(self):
        inv, pol, ans = self._linked_rna()
        result = lc.score(inv, pol, ans)
        self.assertEqual(result['known_field_counts'], {'tp': 3, 'predicted': 3, 'gold': 3})
        method = next(i for i in result['assertion_items'] if i['field_id'] == 'assay:0:method')
        self.assertEqual(method['evidence'][0]['link_path'], [ans['links'][0]['id']])
        self.assertEqual(method['evidence'][0]['fact_owner'], row(inv, 'prediction', 'sample'))

    def test_linked_numeric_condition_can_express_flexible_preparation_time_and_dose(self):
        gold = {'sample':[{'id':'S','material':'RNA after Drug X, 1 uM for 24 hours'}],
                'condition':[{'id':'C','sample_id':'S','target':'Drug X','value':1,
                              'unit':'uM','time':'24 hours'}]}
        pred = copy.deepcopy(gold); pred['sample'][0]['material']='RNA'
        inv = packet(pred,gold,{'sample':['material'],
                              'condition':['sample_id','target','value','unit','time']})
        pol = policy(inv)
        assertion = field_policy(pol,'sample','material')['required_assertions'][0]
        assertion.update(placement='flexible',scope='linked',
                         allowed_evidence=[{'table':'condition','field':f}
                                           for f in ('target','value','unit','time')],
                         basis='The task permits the linked condition to express preparation dose and time.')
        ans = reply(inv,pol); ans['links']=[link(inv,'prediction','condition','sample','sample_id')]
        ev = [evidence(inv,'prediction','sample','material')]+[
              evidence(inv,'prediction','condition',f) for f in ('target','value','unit','time')]
        field = mark(ans,'sample','material'); field['prediction_evidence']=copy.deepcopy(ev)
        field['assertions'][0]['evidence']=copy.deepcopy(ev)
        score = lc.score(inv,pol,ans)
        self.assertEqual(score['known_field_counts'],{'tp':6,'predicted':6,'gold':6})
        ledger = next(a for a in score['assertion_items'] if a['field_id']=='sample:0:material')
        self.assertTrue(all(e['link_path']==[ans['links'][0]['id']] for e in ledger['evidence'][1:]))
        ans['links']=[]
        with self.assertRaisesRegex(ValueError,'disconnected'):lc.score(inv,pol,ans)
        ans['links']=[link(inv,'prediction','condition','sample','sample_id')]
        assertion.update(placement='strict',scope='owner');assertion.pop('allowed_evidence')
        with self.assertRaisesRegex(ValueError,'placement'):lc.score(inv,pol,ans)

    def test_flexible_condition_target_can_use_its_explicitly_linked_preparation_owner(self):
        gold={'sample':[{'id':'S','source':'Bladder urine'}],
              'condition':[{'id':'C','sample_id':'S','target':'Bladder urine preparation'}]}
        pred=copy.deepcopy(gold);pred['condition'][0]['target']='Individual urine preparation'
        inv=packet(pred,gold,{'sample':['source'],'condition':['sample_id','target']})
        pol=policy(inv)
        field_policy(pol,'condition','target')['required_assertions'][0].update(
            placement='flexible',scope='linked',allowed_evidence=[{'table':'sample','field':'source'}],
            basis='The target role and anatomical origin are expressed through this actual sample association.')
        ans=reply(inv,pol);ans['links']=[link(inv,'prediction','condition','sample','sample_id')]
        target=mark(ans,'condition','target')
        ev=[evidence(inv,'prediction','condition','target'),evidence(inv,'prediction','sample','source')]
        target['prediction_evidence']=copy.deepcopy(ev);target['assertions'][0]['evidence']=copy.deepcopy(ev)
        self.assertEqual(lc.score(inv,pol,ans)['field']['tp'],3)
        ans['links'][0]['from_evidence']['quote']='Some other sample'
        with self.assertRaises(ValueError):lc.score(inv,pol,ans)

    def test_disconnected_link_and_wrong_target_are_rejected(self):
        inv, pol, ans = self._linked_rna()
        ans['links'] = []
        with self.assertRaisesRegex(ValueError, 'disconnected'): lc.score(inv, pol, ans)
        inv, pol, ans = self._linked_rna()
        ans['links'][0]['to_evidence']['cell'] = cell(inv, 'prediction', 'assay', 'id')['id']
        ans['links'][0]['to_evidence']['quote'] = 'A'
        with self.assertRaisesRegex(ValueError, 'endpoint'): lc.score(inv, pol, ans)

    def test_software_version_cannot_spread_between_assays_via_shared_sample(self):
        gold = {'sample': [{'id': 'S', 'material': 'RNA'}], 'assay': [
            {'id': 'A', 'sample_id': 'S', 'method': 'tool v2'},
            {'id': 'B', 'sample_id': 'S', 'method': 'tool v2'}]}
        pred = copy.deepcopy(gold); pred['assay'][1]['method'] = None
        inv = packet(pred, gold, {'sample': ['material'], 'assay': ['sample_id', 'method']})
        pol = policy(inv); ans = reply(inv, pol)
        ans['links'] = [link(inv, 'prediction', 'assay', 'sample', 'sample_id', i) for i in range(2)]
        move_expression(mark(ans, 'assay', 'method', 1), evidence(inv, 'prediction', 'assay', 'method', 0))
        with self.assertRaisesRegex(ValueError, 'direct link'): lc.score(inv, pol, ans)
        ev = evidence(inv, 'prediction', 'assay', 'method', 0)
        ev['link_path'] = [ans['links'][1]['id'], ans['links'][0]['id']]
        move_expression(mark(ans, 'assay', 'method', 1), ev)
        with self.assertRaisesRegex(ValueError, 'placement'): lc.score(inv, pol, ans)

    def test_recognizable_analysis_retains_mapping_with_one_wrong_association(self):
        gold = {'result': [{'id': 'g', 'analysis': 'group difference at week 6', 'population_id': 'ITT', 'value': -2}]}
        pred = {'result': [{'id': 'p', 'analysis': 'week 6 between-group difference', 'population_id': 'PP', 'value': -2}]}
        inv = packet(pred, gold, {'result': ['analysis', 'population_id', 'value']})
        pol = policy(inv); ans = reply(inv, pol)
        bad = mark(ans, 'result', 'population_id'); bad['assertions'][0]['verdict'] = 'incorrect'; bad['verdict'] = 'incorrect'
        result = lc.score(inv, pol, ans)
        self.assertEqual(result['known_field_counts'], {'tp': 2, 'predicted': 3, 'gold': 3})
        self.assertEqual(result['record']['tp'], 0)
        self.assertEqual(result['record_items'][0]['verdict'], 'matched')

    def test_different_analysis_with_equal_numbers_is_extra_and_missing(self):
        inv = packet({'result': [{'id': 'p', 'analysis': 'Dose Group primary-dose imputation', 'value': 5}]},
                     {'result': [{'id': 'g', 'analysis': 'Regimen Group after dose changes', 'value': 5}]},
                     {'result': ['analysis', 'value']})
        pol = policy(inv)
        ans = reply(inv, pol, [(row(inv, 'prediction', 'result'), None), (None, row(inv, 'reference', 'result'))])
        result = lc.score(inv, pol, ans)
        self.assertEqual(result['known_field_counts'], {'tp': 0, 'predicted': 2, 'gold': 2})
        self.assertEqual(result['record']['tp'], 0)

    def test_crossover_summary_retains_members_and_both_period_roles(self):
        inv = packet({'population': [{'id': 'p', 'definition': 'The same 22 participants crossed from A to B, 15 weeks in each period.'}]},
                     {'population': [{'id': 'g', 'definition': '22 participants; A then B; period 1 15 weeks; period 2 15 weeks.'}]},
                     {'population': ['definition']})
        pol = policy(inv); ans = reply(inv, pol)
        result = lc.score(inv, pol, ans)
        self.assertEqual(result['known_field_counts'], {'tp': 1, 'predicted': 1, 'gold': 1})

    def test_unsupported_ci_type_fails_whole_field_even_matching_bounds(self):
        inv = packet({'result': [{'id': 'p', 'statistics': '95% CI 1 to 3'}]},
                     {'result': [{'id': 'g', 'statistics': 'reported interval 1 to 3; type unspecified'}]},
                     {'result': ['statistics']})
        pol = policy(inv); ans = reply(inv, pol); bad = mark(ans, 'result', 'statistics')
        bad['integrity'] = {'verdict': 'incorrect', 'evidence': copy.deepcopy(bad['prediction_evidence']),
                            'reason': 'The source never identifies this interval as a 95% confidence interval.'}
        bad['verdict'] = 'incorrect'
        self.assertEqual(lc.score(inv, pol, ans)['known_field_counts'], {'tp': 0, 'predicted': 1, 'gold': 1})

    def test_task_scope_excludes_reference_only_week_ten_and_keeps_week_six_missing(self):
        gold = {'result': [{'id': 'B', 'finding': 'baseline: 10'}, {'id': 'W6', 'finding': 'week 6: 8'},
                           {'id': 'W10', 'finding': 'week 10: 7'}]}
        inv = packet({'result': [gold['result'][0]]}, gold, {'result': ['finding']})
        pol = policy(inv); excluded = field_policy(pol, 'result', 'finding', 2)
        excluded.update(applicable=False, required_assertions=[], applicability={
            'basis': 'The synthetic task explicitly requests baseline and week 6 only.',
            'reason': 'Week 10 is outside the requested time range.', 'source_ids': ['synthetic-task']})
        result = lc.score(inv, pol, reply(inv, pol))
        self.assertEqual(result['known_field_counts'], {'tp': 1, 'predicted': 1, 'gold': 2})
        self.assertEqual((result['record']['tp'], result['record']['predicted'], result['record']['gold']), (1, 1, 2))
        self.assertEqual(result['physical']['field']['gold'], 3)

    def test_explicit_scope_exclusion_is_required_for_submitted_declared_field(self):
        inv = packet({'result': [{'id': 'p', 'finding': 'week 10: 7'}]},
                     {'result': [{'id': 'g', 'finding': 'week 10: 7'}]}, {'result': ['finding']})
        pol = policy(inv); f = field_policy(pol, 'result', 'finding')
        f.update(applicable=False, required_assertions=[], applicability={
            'basis': 'Synthetic task excludes week 10.', 'reason': 'Out-of-scope visit.', 'source_ids': []})
        ans = reply(inv, pol); m = mark(ans, 'result', 'finding')
        m.update(prediction_evidence=[], verdict='not_scored')
        result = lc.score(inv, pol, ans)
        self.assertEqual(result['field']['predicted'], 1)
        ans['unscored'] = [{'cell': cell(inv, 'prediction', 'result', 'finding')['id'],
                            'category': 'out_of_scope', 'reason': 'Only the excluded visit is expressed.',
                            'field_id': f['id'], 'basis': 'The frozen task scope excludes week 10.'}]
        result = lc.score(inv, pol, ans)
        self.assertEqual(result['field']['predicted'], 0)
        self.assertEqual(result['record']['predicted'], 0)

    def test_source_or_library_description_cannot_supply_absent_depth(self):
        inv = packet({'assay': [{'id': 'p', 'depth': None, 'method': 'RNA library prepared'}]},
                     {'assay': [{'id': 'g', 'depth': '10 million reads', 'method': 'RNA library prepared'}]},
                     {'assay': ['depth', 'method']})
        pol = policy(inv); ans = reply(inv, pol)
        result = lc.score(inv, pol, ans)
        self.assertEqual(result['known_field_counts'], {'tp': 1, 'predicted': 1, 'gold': 2})
        forged = evidence(inv, 'prediction', 'assay', 'method', quote='10 million reads')
        move_expression(mark(ans, 'assay', 'depth'), forged)
        with self.assertRaisesRegex(ValueError, 'not expressed'): lc.score(inv, pol, ans)

    def test_invented_replicates_cannot_be_paired_by_count_or_order(self):
        gold = {'sample': [{'id': 'a', 'name': 'condition A aggregate'}, {'id': 'b', 'name': 'condition B aggregate'}]}
        pred = {'sample': [{'id': str(i), 'name': 'invented individual ' + str(i)} for i in range(3)]}
        inv = packet(pred, gold, {'sample': ['name']}); pol = policy(inv)
        pairs = [(r['id'], None) for r in inv['rows'] if r['side'] == 'prediction']
        pairs += [(None, r['id']) for r in inv['rows'] if r['side'] == 'reference']
        result = lc.score(inv, pol, reply(inv, pol, pairs))
        self.assertEqual(result['known_field_counts'], {'tp': 0, 'predicted': 3, 'gold': 2})

    def test_wrong_units_and_direction_count_wrong_expressions_once(self):
        for prediction, reference in [('5 mg/mL', '5 ng/mL'), ('A minus B = 2', 'B minus A = 2')]:
            with self.subTest(prediction=prediction):
                inv = packet({'result': [{'id': 'p', 'finding': prediction}]},
                             {'result': [{'id': 'g', 'finding': reference}]}, {'result': ['finding']})
                pol = policy(inv); ans = reply(inv, pol); bad = mark(ans, 'result', 'finding')
                bad['assertions'][0].update(verdict='incorrect', reason='Native fixture identifies the wrong unit or direction.')
                bad['verdict'] = 'incorrect'
                self.assertEqual(lc.score(inv, pol, ans)['known_field_counts'], {'tp': 0, 'predicted': 1, 'gold': 1})

    def test_explicit_null_absent_and_information_state_are_distinct(self):
        gold = {'result': [{'id': 'g', 'finding': 'not estimable', 'unit': None}]}
        for absent in (False, True):
            pred = {'result': [{'id': 'p', 'finding': 'not estimable', **({} if absent else {'unit': None})}]}
            inv = packet(pred, gold, {'result': ['finding', 'unit']}); pol = policy(inv)
            result = lc.score(inv, pol, reply(inv, pol))
            self.assertEqual(result['known_field_counts'], {'tp': 1, 'predicted': 1, 'gold': 1})
            item = next(i for i in result['field_items'] if i['field'] == 'unit')
            self.assertEqual(item['prediction_field_state'], 'absent' if absent else 'null')
            self.assertEqual(result['record']['tp'], 0 if absent else 1)

    def test_unknown_field_is_counted_unless_explicitly_classified(self):
        inv = packet({'result': [{'id': 'p', 'finding': 3, 'surprise': 'extra scientific claim'}]},
                     {'result': [{'id': 'g', 'finding': 3}]}, {'result': ['finding']})
        pol = policy(inv); ans = reply(inv, pol)
        result = lc.score(inv, pol, ans)
        self.assertEqual(result['known_field_counts'], {'tp': 1, 'predicted': 2, 'gold': 1})
        self.assertEqual(result['record']['tp'], 0)
        self.assertEqual(result['residual_extras'][0]['field'], 'surprise')

    def test_optional_context_needs_policy_permission_and_explicit_native_classification(self):
        inv = packet({'result': [{'id': 'p', 'finding': 3, 'context': 'Interval was not reported.'}]},
                     {'result': [{'id': 'g', 'finding': 3, 'context': None}]}, {'result': ['finding', 'context']})
        pol = policy(inv); ans = reply(inv, pol)
        mark(ans, 'result', 'context').update(prediction_evidence=[], verdict='not_scored')
        self.assertEqual(lc.score(inv, pol, ans)['field']['predicted'], 2)
        exclusion = {'cell': cell(inv, 'prediction', 'result', 'context')['id'],
                     'field_id': 'result:0:context', 'category': 'optional_context',
                     'basis': 'The task does not request an unreported-interval explanation.',
                     'meaning': 'The source-supported NR sentence adds context to the reported result.',
                     'reason': 'Native fixture judges this contextual and source-supported, with no independent attempted statistic.'}
        ans['unscored'] = [exclusion]
        with self.assertRaisesRegex(ValueError, 'permission'): lc.score(inv, pol, ans)
        field_policy(pol, 'result', 'context')['optional_context_allowed'] = True
        self.assertEqual(lc.score(inv, pol, ans)['known_field_counts'], {'tp': 1, 'predicted': 1, 'gold': 1})
        # A different definite scientific attempt is natively left unexcluded.
        wrong = packet({'result': [{'id': 'p', 'finding': 3, 'context': 'Denominator was 999.'}]},
                       {'result': [{'id': 'g', 'finding': 3, 'context': None}]}, {'result': ['finding', 'context']})
        wrong_policy = policy(wrong); field_policy(wrong_policy, 'result', 'context')['optional_context_allowed'] = True
        wrong_reply = reply(wrong, wrong_policy)
        self.assertEqual(lc.score(wrong, wrong_policy, wrong_reply)['known_field_counts'], {'tp': 1, 'predicted': 2, 'gold': 1})

    def test_malformed_unknown_counts_do_not_fabricate_exact_denominators(self):
        inv = packet({'result': 'unreadable table with unknown fields'},
                     {'result': [{'id': 'g', 'finding': 3}]}, {'result': ['finding']})
        pol = policy(inv); ans = reply(inv, pol)
        with self.assertRaisesRegex(ValueError, 'unknown item counts'): lc.score(inv, pol, ans)

    def test_unknown_finals_and_incomplete_coverage_are_rejected(self):
        inv = packet({'sample': [{'id': 'p', 'name': 'A'}]},
                     {'sample': [{'id': 'g', 'name': 'A'}]}, {'sample': ['name']})
        pol = policy(inv)
        for change in ('assertion', 'record', 'field', 'missing_row', 'missing_field'):
            ans = reply(inv, pol)
            if change == 'assertion': ans['fields'][0]['assertions'][0]['verdict'] = 'uncertain'
            elif change == 'record': ans['records'][0]['verdict'] = 'uncertain'
            elif change == 'field': ans['fields'][0]['verdict'] = 'unknown'
            elif change == 'missing_row': ans['records'] = []
            else: ans['fields'] = []
            with self.subTest(change=change), self.assertRaises(ValueError): lc.score(inv, pol, ans)

    def test_real_json_pointer_paths_are_validated(self):
        gold = {'sample': [{'id': 'g', 'detail': {'a/b': ['RNA']}}]}
        pred = {'sample': [{'id': 'p', 'detail': {'a/b': ['RNA']}}]}
        inv = packet(pred, gold, {'sample': ['detail']}); pol = policy(inv); ans = reply(inv, pol)
        ev = evidence(inv, 'prediction', 'sample', 'detail', path='/a~1b/0', quote='RNA')
        move_expression(mark(ans, 'sample', 'detail'), ev)
        self.assertEqual(lc.score(inv, pol, ans)['field']['tp'], 1)
        for badpath in ('/a~1b/1', '/missing', '/a~2b/0', '/a~1b/00'):
            bad = copy.deepcopy(ans); bad['fields'][0]['prediction_evidence'][0]['path'] = badpath
            with self.subTest(path=badpath), self.assertRaises(ValueError): lc.score(inv, pol, bad)

    def test_terminal_zero_helper_refuses_readable_scientific_submissions(self):
        gold = {'sample': [{'id': 'g', 'name': 'A', 'accession': None}]}
        inv = packet({}, gold, {'sample': ['name', 'accession']}); pol = policy(inv)
        result = lc.score(inv, pol, lc.zero_reply(inv, pol))
        self.assertEqual(result['known_field_counts'], {'tp': 0, 'predicted': 0, 'gold': 1})
        nonzero = packet(gold, gold, {'sample': ['name', 'accession']})
        with self.assertRaises(ValueError): lc.zero_reply(nonzero, policy(nonzero))


if __name__ == '__main__':
    unittest.main()

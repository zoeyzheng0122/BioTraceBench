"""Paired restarts reuse native initial history and account for every prior call."""
import copy
import json
import unittest
from pathlib import Path
from unittest.mock import patch

from biotracebench.common import Stop, read, write, sha, verify
from biotracebench.limits import higher_output_limit
from biotracebench.prompts import GSR
from biotracebench.review_retry import prepare
from biotracebench.runner import freeze, run, increase_limits
from test_biotracebench import ANSWER
import test_biotracebench_conditions as fixtures


class ReviewRetryTests(unittest.TestCase):
    setUp = fixtures.ConditionTests.setUp
    tearDown = fixtures.ConditionTests.tearDown
    manifest = fixtures.ConditionTests.manifest
    execute = fixtures.ConditionTests.execute
    send = fixtures.ConditionTests.send
    response = fixtures.ConditionTests.response
    def bounded_manifest(self):
        self.manifest()
        self.frozen.unlink()
        draft = read(self.root/'draft.json')
        draft['model'].setdefault('api_limits', {})['provider_max_output_tokens'] = 8000
        write(self.root/'draft.json', draft)
        return freeze(self.root/'draft.json', self.frozen)

    def stopped_review(self, total_cost=None):
        manifest = self.bounded_manifest()
        if total_cost is not None:
            self.frozen.unlink()
            draft = read(self.root/'draft.json')
            draft['max_total_cost'] = str(total_cost)
            write(self.root/'draft.json', draft)
            manifest = freeze(self.root/'draft.json', self.frozen)
        def sender(*args):
            if 'estimate' in args[0]:
                return self.provider(*args)
            body = json.loads(args[1])
            if body['messages'][-1].get('content') == GSR:
                return self.response(json.dumps(ANSWER)[:10], finish='length')
            return self.send(*args)
        result = self.execute(sender)
        self.assertEqual(result['tasks']['B001']['gsr'], 'paused_truncated')
        return manifest

    def files(self, root):
        return {str(p.relative_to(root)):sha(p) for p in root.rglob('*') if p.is_file()}

    def test_restart_prepares_offline_and_calls_only_both_reviews(self):
        self.stopped_review()
        original = self.files(self.out)
        target = self.root/'new-round'
        calls_before = self.provider.completions
        report = prepare(self.out, ['B001'], {}, target)
        self.assertEqual(report['model_calls'], 0)
        self.assertEqual(report['max_output_tokens'], 2000)
        self.assertEqual(self.provider.completions, calls_before)
        self.assertEqual(verify(target/'B001/i0/final'), verify(self.out/'B001/i0/final'))
        with patch.dict('os.environ', {'MOONSHOT_API_KEY':'synthetic'}):
            result = run(target/'manifest.json', target, sender=self.send)
        self.assertIsNone(result['failure'])
        self.assertEqual(self.provider.completions - calls_before, 2)
        self.assertEqual(read(target/'B001/gsr/branch.json')['i0_history_sha256'],
                         read(target/'B001/ssr/branch.json')['i0_history_sha256'])
        self.assertEqual(original, self.files(self.out))
        costs = read(target/'costs.json')
        self.assertEqual(costs['new_completion_requests'], 2)
        self.assertEqual(len(costs['calls']), 4)
        self.assertEqual(sum(r['stage']=='i0' for r in costs['calls']), 1)
        self.assertEqual(sum(bool(r.get('historical_round')) for r in costs['calls']), 1)
        before_replay = self.provider.completions
        replay = run(target/'manifest.json', target, offline=True,
                     sender=lambda *a: self.fail('Offline replay sent a request'))
        self.assertIsNone(replay['failure'])
        self.assertEqual(self.provider.completions, before_replay)
        self.assertEqual(original, self.files(self.out))

    def test_started_review_cannot_extend_in_place(self):
        self.stopped_review()
        with self.assertRaises(Stop) as error:
            increase_limits(self.frozen, self.out, {'max_output_tokens':2000}, targets=['B001/gsr'])
        self.assertEqual(error.exception.status, 'review_restart_required')
        self.assertFalse((self.out/'limit-extensions').exists())

    def test_pre_review_extension_includes_both_branches(self):
        self.bounded_manifest()
        def sender(*args):
            if 'estimate' in args[0]:return self.provider(*args)
            return self.response('{',finish='length')
        self.execute(sender)
        increase_limits(self.frozen,self.out,{'max_total_tokens':200000},targets=['B001/gsr'])
        from biotracebench.limits import extensions, effective
        manifest=read(self.frozen)
        history=extensions(manifest,self.out)
        self.assertEqual(set(history[0]['targets']),{'B001/gsr','B001/ssr'})
        self.assertEqual(effective(manifest,history,'B001','gsr')['budgets']['gsr']['max_total_tokens'],200000)
        self.assertEqual(effective(manifest,history,'B001','ssr')['budgets']['ssr']['max_total_tokens'],200000)
        self.assertEqual(effective(manifest,history,'B001','i0')['budgets']['i0']['max_total_tokens'],100000)

    def test_retry_enforces_provider_ceiling(self):
        self.stopped_review()
        with self.assertRaisesRegex(ValueError, 'provider ceiling'):
            prepare(self.out, ['B001'], {'max_output_tokens':9000}, self.root/'invalid')
        self.assertFalse((self.root/'invalid').exists())

    def test_default_candidate_is_clamped_and_no_larger_value_is_rejected(self):
        model = {'max_output_tokens':3000,'context_tokens':10000,
                 'api_limits':{'provider_max_output_tokens':5000}}
        self.assertEqual(higher_output_limit(model), 5000)
        model['max_output_tokens'] = 5000
        with self.assertRaisesRegex(ValueError, 'cannot increase'):
            higher_output_limit(model)
        del model['api_limits']['provider_max_output_tokens']
        with self.assertRaisesRegex(ValueError, 'verified'):
            higher_output_limit(model)

    def test_old_rounds_are_included_once_across_multiple_retries(self):
        self.bounded_manifest()
        self.execute()
        first, second = self.root/'first-retry', self.root/'second-retry'
        prepare(self.out, ['B001'], {}, first)
        with patch.dict('os.environ', {'MOONSHOT_API_KEY':'synthetic'}):
            self.assertIsNone(run(first/'manifest.json', first, sender=self.send)['failure'])
        prepare(first, ['B001'], {}, second)
        with patch.dict('os.environ', {'MOONSHOT_API_KEY':'synthetic'}):
            self.assertIsNone(run(second/'manifest.json', second, sender=self.send)['failure'])
        costs = read(second/'costs.json')
        self.assertEqual(costs['completion_requests'], 7)
        self.assertEqual(costs['new_completion_requests'], 2)
        self.assertEqual(sum(r['stage']=='i0' for r in costs['calls']), 1)
        self.assertEqual(read(second/'manifest.json')['review_retry']['round'], 2)
        self.assertEqual(len({(r.get('origin_run',str(second)),r['attempt']) for r in costs['calls']}), 7)

    def test_retry_checks_remaining_experiment_budget_before_creation(self):
        from biotracebench.cost import upper
        from test_biotracebench import TARIFF
        self.stopped_review(total_cost=2*upper(200,1000,TARIFF))
        with self.assertRaises(Stop) as error:
            prepare(self.out, ['B001'], {}, self.root/'too-expensive')
        self.assertEqual(error.exception.status, 'paused_budget')
        self.assertFalse((self.root/'too-expensive').exists())

    def test_cli_prepares_a_new_round_without_dispatch(self):
        self.stopped_review()
        from biotracebench.cli import main
        from contextlib import redirect_stdout
        import io
        target = self.root/'cli-round'
        write(self.root/'limits.json', {})
        before = self.provider.completions
        stream = io.StringIO()
        with redirect_stdout(stream):
            self.assertEqual(main(['review-retry','--run',str(self.out),'--case','B001',
                '--limits',str(self.root/'limits.json'),'--out',str(target)]), 0)
        self.assertEqual(json.loads(stream.getvalue())['status'], 'review_round_prepared')
        self.assertEqual(self.provider.completions, before)

    def test_reused_initial_and_inherited_costs_are_bound_to_manifest(self):
        self.stopped_review()
        target = self.root/'retry'
        prepare(self.out, ['B001'], {}, target)
        costs = read(target/'inherited-costs.json')
        costs[0]['amount'] = '0'
        write(target/'inherited-costs.json', costs)
        with self.assertRaises(Stop) as error:
            run(target/'manifest.json', target, offline=True)
        self.assertEqual(error.exception.status, 'tampered')

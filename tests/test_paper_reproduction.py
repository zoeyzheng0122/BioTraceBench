import gzip
import json
from pathlib import Path
import tempfile
import unittest
from biotracebench_analysis.paper_reproduction import read, summarize, resource_summary

class PaperReproductionTests(unittest.TestCase):
    def test_reads_compressed_archived_judgments(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'judgment.json.gz'
            judgment={'marking': {'cells': []}, 'label': '科学内容'}
            path.write_bytes(gzip.compress(json.dumps(judgment).encode()))
            self.assertEqual(read(path),judgment)
    def test_cross_model_comparison_uses_paired_initial_outputs(self):
        rows=[]
        for model,value in [('a',1),('b',0)]:
            for case,domain in [('B1','basic'),('C1','clinical')]:
                for condition in ('i0','gsr','ssr'):
                    rows.append(dict(model=model,case=case,domain=domain,condition=condition,
                        **{l+'_'+metric:value for l in ('field','record') for metric in ('precision','recall','f1')}))
        r=summarize(rows,{'seed':20261110,'resamples':100,'interval':[.025,.975],
                         'quantile_method':'linear','domain_weights':{'basic':.5,'clinical':.5}})
        pair=next(x for x in r['cross_model'] if x['domain']=='overall')
        self.assertEqual((pair['model_a'],pair['model_b']),('a','b'))
        self.assertEqual(pair['field_f1']['mean'],1)
        self.assertEqual(pair['field_f1']['low'],1)
    def test_equal_domain_weight_and_direct_f1_averaging(self):
        rows=[]
        for case,domain,value in [('B1','basic',1),('B2','basic',1),('C1','clinical',0)]:
            for condition in ('i0','gsr','ssr'):
                rows.append(dict(model='m',case=case,domain=domain,condition=condition,
                    **{l+'_'+metric:value for l in ('field','record') for metric in ('precision','recall','f1')}))
        result=summarize(rows,{'seed':20261110,'resamples':100,'interval':[.025,.975],
            'quantile_method':'linear','domain_weights':{'basic':.5,'clinical':.5}})
        overall=next(r for r in result['summary'] if r['domain']=='overall' and r['stage']=='i0')
        self.assertEqual(overall['field_f1'],{'mean':.5,'low':.5,'high':.5})
        change=next(r for r in result['delta'] if r['domain']=='overall')
        self.assertEqual(change['field_f1']['unchanged'],3)
        self.assertEqual(change['field_f1']['mean'],0)
    def test_unknown_request_usage_does_not_become_zero_or_billed_cost(self):
        positions=[dict(model='m',case='B1',condition=s,currency='USD',eligible=True) for s in ('i0','gsr','ssr')]
        requests=[dict(model='m',case='B1',condition='i0',included=True,confirmed=True,input_tokens=10,output_tokens=2,total_tokens=12,tariff_estimate='0.1',cost_upper_bound='0.1',reserved_amount=None,billed_actual=None),
                  dict(model='m',case='B1',condition='gsr',included=True,confirmed=True,input_tokens=None,output_tokens=None,total_tokens=None,tariff_estimate=None,cost_upper_bound='0.5',reserved_amount=None,billed_actual=None)]
        result=resource_summary({'positions':positions,'requests':requests})
        r=next(r for r in result['summary'] if r['workflow']=='i0+gsr')
        self.assertEqual(r['total_tokens']['n'],0)
        self.assertIsNone(r['total_tokens']['mean'])
        self.assertEqual(r['billed_actual']['n'],0)
        self.assertEqual(result['unknown_consumption_upper_bounds']['USD'],'0.5')

if __name__=='__main__':unittest.main()

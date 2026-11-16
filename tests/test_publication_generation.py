"""The publication default executes one native construction phase."""
import unittest
from biotracebench.common import read,write
from biotracebench.runner import freeze
import test_biotracebench_conditions as fixtures

class GenerationOnlyTests(unittest.TestCase):
 setUp=fixtures.ConditionTests.setUp
 tearDown=fixtures.ConditionTests.tearDown
 execute=fixtures.ConditionTests.execute
 send=fixtures.ConditionTests.send
 def test_one_completion_and_exact_offline_recovery(self):
  fixtures.ConditionTests.manifest(self);draft=read(self.root/'draft.json');draft.update(scope='generation',stages=['i0'],budgets={'i0':draft['budgets']['i0']});write(self.root/'published-draft.json',draft);self.frozen=self.root/'published-manifest.json';freeze(self.root/'published-draft.json',self.frozen)
  result=self.execute();self.assertIsNone(result['failure']);self.assertEqual(set(result['tasks']['B001']),{'i0'});self.assertEqual(self.provider.completions,1)
  snapshot=read(self.out/'B001/i0/final/snapshot.json');self.assertTrue(snapshot['messages']);before=self.provider.completions;self.assertIsNone(self.execute(offline=True)['failure']);self.assertEqual(self.provider.completions,before)
if __name__=='__main__':unittest.main()

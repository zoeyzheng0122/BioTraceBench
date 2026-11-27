"""Shared rules must be reachable from every published case prompt."""
from pathlib import Path
import re
import unittest


class DatasetLinkTests(unittest.TestCase):
    def test_case_prompts_link_to_existing_shared_rules(self):
        data = Path(__file__).resolve().parents[1]/'data'
        cases = sorted(data.glob('[BC][0-9][0-9][0-9]'))
        self.assertEqual(len(cases), 100)
        for case in cases:
            for name in ('query.md', 'generation-prompt.md'):
                with self.subTest(case=case.name, prompt=name):
                    links = [target for target in re.findall(r'\]\(([^)]+)\)', (case/name).read_text())
                             if 'shared/' in target]
                    self.assertEqual(len(links), 1)
                    self.assertTrue((case/links[0]).is_file(), links[0])

"""Synthetic checks of overlapping diagnostics and unchanged score aggregation."""
from copy import deepcopy
import unittest
from biotracebench_analysis.publication.diagnostics import binding_summary, task_groups
from biotracebench_analysis.publication.statistics import METRICS

class DiagnosticTests(unittest.TestCase):
    def event(self, i, case, subtype):
        return dict(event_id=str(i), model="model", case=case, subtype=subtype,
                    basis="Explicit source premise", evidence=[{"locator":"source passage"}], status="resolved")
    def test_intersections_restore_union(self):
        events=[self.event(1,"A","object_identity"), self.event(2,"A","relationship_role"),
                self.event(3,"B","relation_context_omission"),self.event(4,"C","relationship_role")]
        r=binding_summary(events,{("model","A"):"pass",("model","B"):"pass"},
                          {("model",c) for c in "ABC"})
        self.assertEqual(r["evaluable"]["binding_answers"],3)
        self.assertEqual(r["structure_pass"]["binding_answers"],2)
        self.assertEqual(sum(r["structure_pass"]["exact_intersections"].values()),2)
        self.assertEqual(r["structure_pass"]["subtypes"]["relationship_role"],1)
    def test_repeated_event_fails(self):
        event=self.event(1,"A","object_identity")
        with self.assertRaises(ValueError):binding_summary([event,event],{}, {("model","A")})
    def test_pending_label_fails(self):
        event=self.event(1,"A","object_identity");event["status"]="pending"
        with self.assertRaises(ValueError):binding_summary([event],{}, {("model","A")})
    def test_zeros_undefined_and_domain_weighting(self):
        annotations=[dict(case=c,domain=d,tags=["temporal_context"],basis="Task timing",evidence=["task"])
                     for c,d in [("A","basic"),("B","basic"),("C","clinical")]]
        scores=[dict(case=c,domain=d,model="model",zero_output=z,
                     **{q:None if c=="B" and q.startswith("record") else v for q in METRICS})
                for c,d,v,z in [("A","basic",0.8,"False"),("B","basic",0.,"True"),("C","clinical",1.,"False")]]
        original=deepcopy(scores);coverage,groups=task_groups(annotations,scores)
        r=next(r for r in groups if r["tag"]=="temporal_context" and r["domain"]=="overall")
        self.assertAlmostEqual(r["field_f1"],.7);self.assertAlmostEqual(r["record_f1"],.9)
        self.assertEqual(r["field_f1_n"],3);self.assertEqual(r["record_f1_n"],2)
        self.assertEqual(r["assigned_zeros"],1);self.assertEqual(scores,original)
    def test_incomplete_task_coverage_fails(self):
        with self.assertRaises(ValueError):task_groups([], [dict(model="m",case="A")])

if __name__=="__main__":unittest.main()

"""Tiny descriptive-summary unit fixtures; never experimental evidence."""
import importlib.util
from pathlib import Path
import unittest

import pandas as pd

P = Path(__file__).resolve().parents[1]/"summarize_results.py"
spec = importlib.util.spec_from_file_location("summarize_results", P)
m = importlib.util.module_from_spec(spec)
if P.exists():
    spec.loader.exec_module(m)


class SummaryTests(unittest.TestCase):
    def test_api_exists(self):
        self.assertTrue(callable(getattr(m,"build_summary",None)))

    def test_seed_summary_averages_identity_then_seed_not_opportunities(self):
        d = pd.DataFrame(dict(matched_seed=[1,1,2,2],
                              exact_rate=[0,.2,.6,.8],
                              n_opportunities=[1000,10,100,100]))
        s = m.seed_summary(d,"exact_rate")
        self.assertAlmostEqual(s["mean"], .4)
        self.assertAlmostEqual(s["minimum"], .1)
        self.assertAlmostEqual(s["maximum"], .7)
        self.assertEqual(s["n_seeds"], 2)
        self.assertEqual(len(s["seed_values"]),2)

    def test_partial_data_rejected_even_if_proof_claims_complete(self):
        d = pd.DataFrame([dict(topic_key="retirement",horizon=30,
                              matched_seed=1,cell_id="SIS-A0-B0",cohort="unit",n=500,n_events=15000)])
        with self.assertRaises(ValueError):
            m.validate_coverage(d,dict(completed_horizon_trajectories=102,unique_network_events=1890000))

    def test_unit_bypass_is_explicit_and_marked(self):
        d = pd.DataFrame([dict(topic_key="unit",horizon=1,matched_seed=1,
                              cell_id="SIS-A0-B0",cohort="unit",n=4,n_events=4)])
        result = m.validate_coverage(d,{},unit_test_mode=True)
        self.assertTrue(result["unit_fixture_only"])

    def test_undefined_rates_are_not_zero_filled(self):
        d = pd.DataFrame(dict(matched_seed=[1,1,2,2],x=[None,None,.2,.6]))
        s = m.seed_summary(d,"x")
        self.assertEqual(s["n_seeds"],1)
        self.assertEqual(s["n_seeds_missing"],1)
        self.assertAlmostEqual(s["mean"],.4)

    def test_results_and_discussion_word_counts(self):
        panels=[]
        for label in ["Retirement T30 (n=10 seeds)","Retirement T60 (n=3 seeds)",
                      "GM market sales T60 (n=2 seeds)","AI job loss T60 (n=2 seeds)"]:
            panels.append(dict(label=label,a1_direct_events={},a1_dominant={},b1_endpoint={},
                               a2_directional={},a2_asymmetry={},b1_topology_b2_minus_b1={},
                               b2_excess_topology={},b3_identity_effects={},b4_gap={}))
        for render in (m._rq2a,m._rq2b,m._rq3):
            text=render(dict(panels=panels))
            self.assertGreaterEqual(len(text["results"].split()),120)
            self.assertLessEqual(len(text["results"].split()),180)
            self.assertGreaterEqual(len(text["discussion"].split()),90)
            self.assertLessEqual(len(text["discussion"].split()),115)

    def test_paired_difference_formatter_uses_percentage_points(self):
        text=m._stat(dict(mean=.1,minimum=-.2,maximum=.4,n_seeds=2),percentage_points=True)
        self.assertIn("10.00pp",text)
        self.assertIn("-20.00pp",text)

    def test_full_tiny_fixture_metrics_to_numeric_brief(self):
        def module(name,path):
            s=importlib.util.spec_from_file_location(name,path)
            x=importlib.util.module_from_spec(s)
            s.loader.exec_module(x)
            return x
        fixture_module=module("unit_fixture_rq3",P.parent/"tests/test_metrics_rq3.py")
        rq2=module("unit_rq2",P.parent/"metrics_rq2.py")
        rq3=module("unit_rq3",P.parent/"metrics_rq3.py")
        tables={}
        for a in [0,1]:
            for b in [0,1,2]:
                r=fixture_module.fixture(f"SIS-A{a}-B{b}")
                if b==0:
                    r["edges"],r["feed"]=[],pd.DataFrame()
                for analysis in (rq2.analyze_run(r),rq3.analyze_run(r,permutations=0)):
                    for name,rows in analysis.items():tables.setdefault(name,[]).extend(rows)
        tables.update(rq3.paired_results(tables))
        result=m.build_summary({k:pd.DataFrame(v) for k,v in tables.items()}, {},unit_test_mode=True)
        self.assertTrue(result["coverage"]["unit_fixture_only"])
        self.assertEqual(len(result["panels"]),1)
        p=result["panels"][0]
        self.assertEqual(p["b1_endpoint"]["B1"]["variance"]["mean"],1)
        self.assertEqual(p["b4_gap"]["B1"]["private_stock_tv"]["mean"],.5)
        self.assertEqual(p["b2_excess_topology"]["unrestricted"]["mean"],0)
        self.assertEqual(p["a1_dominant"]["3"]["B1"]["cumulative_net_flow"]["mean"],2)
        self.assertEqual(p["a1_direct_events"]["B1"]["direct_5_to_3"]["mean"],0)
        self.assertEqual(len(p["a2_directional_actual_cells"]),12)
        self.assertIn("500 posts",m._detail_b4(result))
        self.assertIn("B0",m._detail_b1(result))
        for render in (m._rq2a,m._rq2b,m._rq3):
            self.assertIn("unit T1",render(result)["table"])
        with self.assertRaises(ValueError):
            m.write_reports(result,Path("UNITS-A"),Path("UNITS-B"),Path("UNITS.json"))

    def test_rq3_states_lower_local_alignment_when_actual_difference_negative(self):
        stat=lambda x:dict(mean=x,minimum=x,maximum=x,n_seeds=1)
        p=dict(label="UNIT T60",b1_topology_b2_minus_b1=stat(.2),
               b2_excess_topology={"unrestricted":stat(-.1)},b3_identity_effects={},b4_gap={})
        result=m._rq3(dict(panels=[p]))
        self.assertIn("excess alignment was lower",result["results"])


if __name__ == "__main__":unittest.main()

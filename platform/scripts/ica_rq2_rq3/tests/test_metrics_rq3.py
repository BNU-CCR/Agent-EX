"""Tiny unit fixtures, not experimental observations."""
import importlib.util
from pathlib import Path
import unittest

import numpy as np
import pandas as pd

PATH = Path(__file__).resolve().parents[1] / "metrics_rq3.py"
spec = importlib.util.spec_from_file_location("metrics_rq3", PATH)
m = importlib.util.module_from_spec(spec)
if PATH.exists():
    spec.loader.exec_module(m)


def fixture(cell="A0B1"):
    return dict(meta=dict(topic_key="unit", matched_seed=7, cell_id=cell,
                          run_id=cell, cohort="unit", horizon=1),
                node_ids=["a", "b", "c", "d"],
                groups=dict(a="Blue", b="Blue", c="Green", d="Green"),
                initial_stances=dict(a=1, b=1, c=7, d=7),
                initial_public=dict(a=1, b=1, c=7, d=7),
                edges=[("a", "b"), ("b", "c"), ("c", "d")],
                events=pd.DataFrame([
                    dict(ordinal=0, agent_id="a", before=1, after=3, published=False),
                    dict(ordinal=1, agent_id="b", before=1, after=3, published=True),
                    dict(ordinal=2, agent_id="c", before=7, after=5, published=False),
                    dict(ordinal=3, agent_id="d", before=7, after=5, published=True)]),
                feed=pd.DataFrame([
                    dict(ordinal=0, receiver_agent_id="a", display_slot=0,
                         source_agent_id="c", source_stance=7, publication_ordinal=None),
                    dict(ordinal=0, receiver_agent_id="a", display_slot=1,
                         source_agent_id="c", source_stance=7, publication_ordinal=None),
                    dict(ordinal=1, receiver_agent_id="b", display_slot=0,
                         source_agent_id="c", source_stance=7, publication_ordinal=None)]))


class RQ3Tests(unittest.TestCase):
    def test_api_exists(self):
        self.assertTrue(callable(getattr(m, "analyze_run", None)))

    def test_state_replay_and_public_stock_are_separate(self):
        tables = m.analyze_run(fixture(), permutations=9)
        rows = tables["B1_time_trajectories"]
        self.assertEqual([r["round"] for r in rows], [0, 1])
        self.assertEqual(rows[0]["variance"], 9)
        self.assertEqual(rows[1]["variance"], 1)
        self.assertEqual(rows[1]["variance_change_from_r0"], -8)
        dist = {r["layer"]: r for r in tables["B4_private_public_distributions"] if r["round"] == 1}
        self.assertEqual(dist["private_state"]["count_3"], 2)
        self.assertEqual(dist["public_stock"]["count_1"], 1)
        self.assertEqual(dist["public_flow"]["n"], 2)
        gap = tables["B4_visibility_gap_by_round"][-1]
        self.assertEqual(gap["mean_agent_private_public_abs_gap"], 1)
        self.assertEqual(gap["private_stock_tv"], .5)
        self.assertEqual(gap["private_stock_wasserstein"], 1)
        self.assertEqual(tables["B4_public_stock_age"][-1]["fraction_age_ge_1"], .5)

    def test_undirected_assortativity_and_exact_null(self):
        x = np.array([1, 1, 7, 7])
        edges = np.array([[0, 1], [1, 2], [2, 3]])
        stats = m.edge_statistics(x, edges)
        self.assertAlmostEqual(stats["assortativity"], 1 / 3)
        self.assertIsNone(m.edge_statistics(np.ones(4), edges)["assortativity"])
        out = m.analyze_run(fixture(), permutations=19)
        null = [r for r in out["B2_permutation_baselines"] if r["round"] == 0 and r["edge_scope"] == "all"]
        self.assertEqual(len(null), 2)
        self.assertAlmostEqual(next(r for r in null if r["permutation_mode"] == "unrestricted")["expected_same_stance_fraction"], 1/3)
        self.assertAlmostEqual(next(r for r in null if r["permutation_mode"] == "within_group")["expected_same_stance_fraction"], 2/3)
        self.assertEqual(out, m.analyze_run(fixture(), permutations=19))

    def test_permutations_preserve_correct_margins(self):
        x = np.array([1, 2, 3, 4, 5, 6])
        g = np.array(["Blue"] * 3 + ["Green"] * 3)
        for mode in ["unrestricted", "within_group"]:
            for p in m.permuted_stances(x, g, mode, np.random.default_rng(91), 20):
                self.assertEqual(sorted(x), sorted(p))
                if mode == "within_group":
                    for group in set(g):
                        self.assertEqual(sorted(x[g == group]), sorted(p[g == group]))

    def test_feed_is_slot_based_but_updates_are_event_based(self):
        out = m.analyze_run(fixture(), permutations=0)
        r = out["B2_realized_exposure_homophily"][-1]
        self.assertEqual(r["n_slots"], 3)
        self.assertEqual(r["same_stance_fraction"], 0)
        self.assertEqual(r["repeated_post_within_receiver_slots"], 1)
        self.assertEqual(r["repeated_post_across_receivers_slots"], 1)
        cond = out["B3_source_conditional_updating"]
        self.assertEqual(sum(r["n_events"] for r in cond), 4)
        fed = [r for r in cond if r["source_group_mix"] != "no_feed"]
        self.assertEqual(sum(r["n_events"] for r in fed), 2)
        self.assertEqual(sum(r["n_move_toward_feed"] for r in fed), 2)

    def test_fail_closed_replay_and_future_post(self):
        r = fixture()
        r["events"].loc[0, "before"] = 2
        with self.assertRaises(ValueError):
            m.analyze_run(r, permutations=0)

    def test_old_publication_and_distinct_same_source_posts_remain_valid(self):
        r = fixture()
        r["meta"]["horizon"] = 2
        more = r["events"].copy()
        more["ordinal"] += 4
        more["before"] = more["after"]
        more["published"] = False
        r["events"] = pd.concat([r["events"], more], ignore_index=True)
        r["feed"] = pd.concat([r["feed"], pd.DataFrame([
            dict(ordinal=4, receiver_agent_id="a", display_slot=0,
                 source_agent_id="b", source_stance=1, publication_ordinal=None),
            dict(ordinal=4, receiver_agent_id="a", display_slot=1,
                 source_agent_id="b", source_stance=3, publication_ordinal=1),
            dict(ordinal=4, receiver_agent_id="a", display_slot=2,
                 source_agent_id="c", source_stance=7, publication_ordinal=None)])], ignore_index=True)
        out = m.analyze_run(r, permutations=0)
        feed = out["B2_realized_exposure_homophily"][-1]
        self.assertEqual(feed["n_slots"], 3)
        self.assertEqual(feed["repeated_post_within_receiver_slots"], 1)
        self.assertEqual(feed["repeated_source_within_receiver_slots"], 2)
        self.assertEqual(out["B4_public_stock_age"][-1]["fraction_age_ge_1"], 1)
        self.assertEqual(out["B4_private_public_distributions"][-3]["n"], 0)
        self.assertIsNone(out["B4_private_public_distributions"][-3]["mean"])

    def test_reason_change_missing_is_not_zero_and_known_counts_are_separate(self):
        r = fixture()
        out = m.analyze_run(r, permutations=0)
        self.assertIsNone(out["B1_global_convergence_by_run"][0]["reason_change_rate"])
        r["events"]["reason_changed"] = [True, False, None, True]
        out = m.analyze_run(r, permutations=0)
        row = out["B1_global_convergence_by_run"][0]
        self.assertEqual(row["n_reason_change_known"], 3)
        self.assertEqual(row["n_reason_changed"], 2)
        self.assertEqual(row["reason_change_rate"], 2/3)

    def test_noninteger_initial_state_is_rejected(self):
        r = fixture()
        r["initial_stances"]["a"] = 1.5
        with self.assertRaises(ValueError):
            m.analyze_run(r, permutations=0)

    def test_weighted_with_replacement_round_keeps_population_and_state_chain(self):
        r = fixture()
        r["events"] = pd.DataFrame([
            dict(ordinal=0, agent_id="a", before=1, after=3, published=False),
            dict(ordinal=1, agent_id="a", before=3, after=5, published=True),
            dict(ordinal=2, agent_id="c", before=7, after=5, published=False),
            dict(ordinal=3, agent_id="c", before=5, after=3, published=True)])
        r["feed"] = pd.DataFrame()
        out = m.analyze_run(r, permutations=0)
        row = out["B1_time_trajectories"][-1]
        self.assertEqual(row["n"], 4)
        self.assertEqual(row["mean"], 4)
        self.assertEqual(row["variance"], 5)
        self.assertEqual([row[f"count_{k}"] for k in [1,3,5,7]], [1,1,1,1])
        self.assertEqual(sum(x["n_events"] for x in out["B3_source_conditional_updating"]), 4)
        r["events"].loc[1, "before"] = 1
        with self.assertRaises(ValueError):
            m.analyze_run(r, permutations=0)
        r = fixture()
        r["feed"].loc[0, "publication_ordinal"] = 2
        with self.assertRaises(ValueError):
            m.analyze_run(r, permutations=0)

    def test_pairing_horizon_cohort_and_no_undefined_b0_edge_fill(self):
        merged = {}
        for a in [0, 1]:
            for b in [0, 1, 2]:
                r = fixture(f"A{a}B{b}")
                if b == 0:
                    r["edges"] = []
                    r["feed"] = pd.DataFrame()
                for key, vals in m.analyze_run(r, permutations=0).items():
                    merged.setdefault(key, []).extend(vals)
        out = m.paired_results(merged)
        self.assertEqual(len(out["B1_paired_network_effects"]), 4)
        self.assertEqual(len(out["B1_topology_contrasts"]), 2)
        identity = out["B3_identity_effects_by_seed"]
        self.assertEqual(len(identity), 3)
        self.assertEqual(identity[0]["variance_a1_minus_a0"], 0)
        interactions = out["B3_identity_network_interactions"]
        did = [r for r in interactions if r["contrast_type"] == "identity_network_did_vs_b0"]
        self.assertEqual(len(did), 2)
        self.assertTrue(all(r["excess_same_stance_unrestricted_did"] is None for r in did))

    def test_empty_exposure_counts_and_repeat_fractions_are_explicit(self):
        r = fixture("A0B0")
        r["edges"], r["feed"] = [], pd.DataFrame()
        row = m.analyze_run(r, permutations=0)["B2_realized_exposure_homophily"][-1]
        self.assertEqual(row["repeated_post_within_receiver_slots"], 0)
        self.assertIsNone(row["repeated_post_within_receiver_fraction"])
        row = m.analyze_run(fixture(), permutations=0)["B2_realized_exposure_homophily"][-1]
        self.assertEqual(row["repeated_post_within_receiver_fraction"], 1/3)

    def test_pairing_numerical_did_and_zero_b0_percent(self):
        endpoints = []
        for a in [0, 1]:
            for b in [0, 1, 2]:
                r = m.analyze_run(fixture(f"A{a}B1"), permutations=0)["B1_global_convergence_by_run"][0]
                r["cell_id"] = f"A{a}B{b}"
                r["run_id"] = r["cell_id"]
                r["variance"] = [0, 2, 3][b]+a*[1, 3, 5][b]
                endpoints.append(r)
        result = m.paired_results({"B1_global_convergence_by_run": pd.DataFrame(endpoints)})
        net = result["B1_paired_network_effects"][0]
        self.assertEqual(net["network_effect_variance"], 2)
        self.assertIsNone(net["network_effect_variance_pct_of_b0"])
        interactions = result["B3_identity_network_interactions"]
        did = next(x for x in interactions if x["network_condition"] == "B1")
        self.assertEqual(did["variance_did"], 2)
        endpoints[0]["cohort"] = "other_cohort"
        result = m.paired_results({"B1_global_convergence_by_run": endpoints})
        self.assertEqual(len(result["B1_paired_network_effects"]), 2)


if __name__ == "__main__":
    unittest.main()

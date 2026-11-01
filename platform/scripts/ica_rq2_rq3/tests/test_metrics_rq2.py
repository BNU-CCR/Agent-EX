"""Small UNIT fixtures only: these are not scientific observations/results."""
import importlib.util
from pathlib import Path
import unittest

import pandas as pd

MODULE = Path(__file__).resolve().parents[1] / 'metrics_rq2.py'


def unit_run():
    # a takes 3 -> 4 -> 5 -> 3; only the final jump is direct 5 -> 3.
    rows = [(0, 'a', 3, 4, False), (1, 'b', 5, 3, True),
            (2, 'a', 4, 5, True), (3, 'b', 3, 5, False),
            (4, 'a', 5, 3, True), (5, 'b', 5, 5, True)]
    events = pd.DataFrame(rows, columns=['ordinal', 'agent_id', 'before', 'after', 'published'])
    events['reason_changed'] = None
    feed = pd.DataFrame([(0, 'a', 0, 'b', 5, None, 'b0'),
                         (0, 'a', 1, 'b', 5, None, 'b0'),
                         (1, 'b', 0, 'a', 3, None, 'a0'),
                         (2, 'a', 0, 'b', 3, 1, 'b1'),
                         (3, 'b', 0, 'a', 5, 2, 'a2'),
                         (4, 'a', 0, 'b', 3, 1, 'b1')],
                        columns=['ordinal', 'receiver_agent_id', 'display_slot', 'source_agent_id',
                                 'source_stance', 'publication_ordinal', 'post_id'])
    return dict(meta=dict(topic_key='UNIT', matched_seed=7, cell_id='SIS-A0-B1',
                          run_id='UNIT_ONLY', cohort='UNIT', horizon=3),
                node_ids=['a', 'b'], groups={'a': 'Blue', 'b': 'Green'},
                initial_stances={'a': 3, 'b': 5}, initial_public={'a': 3, 'b': 5},
                edges=[('a', 'b')], events=events, feed=feed)


class MetricsUnitTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if MODULE.exists():
            spec = importlib.util.spec_from_file_location('metrics_rq2', MODULE)
            cls.mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(cls.mod)
        else:
            cls.mod = None

    def analyze(self, run=None):
        self.assertIsNotNone(self.mod, 'offline metrics module is not implemented')
        return self.mod.analyze_run(unit_run() if run is None else run)

    def test_transition_conservation_and_paths(self):
        tables = self.analyze()
        matrix = pd.DataFrame(tables['A1_round_transition_matrices'])
        self.assertEqual(len(matrix), 147)
        self.assertEqual(matrix.groupby('round')['count'].sum().tolist(), [2, 2, 2])
        flow = pd.DataFrame(tables['A1_net_stance_flows'])
        self.assertTrue((flow['net_flow'] == flow['population_count'] - flow['previous_count']).all())
        self.assertTrue((flow['cumulative_net_flow'] == flow['population_count'] - flow['round0_count']).all())
        paths = {r['agent_id']: r for r in tables['A1_origin_destination_paths']}
        self.assertEqual(paths['a']['direct_3_to_5_count'], 0)
        self.assertEqual(paths['a']['via4_3_to_5_count'], 1)
        self.assertEqual(paths['a']['direct_5_to_3_count'], 1)
        self.assertIsNone(paths['a']['stance_r30'])

    def test_feed_counts_event_denominators_public_state_and_history(self):
        tables = self.analyze()
        ev = tables['A2_event_exposure_numeric']
        self.assertEqual(ev[0]['feed_length'], 2)
        self.assertEqual(ev[0]['distance_numerator'], 4)
        self.assertEqual(ev[0]['duplicate_source_slots'], 1)
        self.assertEqual(ev[2]['public_before'], 3)  # unpublished update to 4 stays private
        self.assertEqual(ev[4]['prior_source_exposures'], 3)
        self.assertEqual(ev[4]['repeat_post_slots'], 1)
        self.assertEqual(ev[5]['exposure_class'], 'no_feed')
        cells = tables['A2_exposure_response_cells']
        self.assertEqual(sum(r['denominator'] for r in cells), 6)
        directional = tables['A2_directional_update_rates']
        exact53 = next(r for r in directional if r['prior_stance'] == 5 and r['target_stance'] == 3)
        self.assertEqual(exact53['n_opportunities'], 2)
        self.assertEqual(exact53['n_exact_i_to_j'], 2)
        exact35 = next(r for r in directional if r['prior_stance'] == 3 and r['target_stance'] == 5)
        self.assertEqual(exact35['n_opportunities'], 2)
        self.assertEqual(exact35['n_exact_i_to_j'], 1)
        self.assertEqual(exact35['n_toward_target'], 2)
        self.assertIsNone(next(r for r in directional if r['prior_stance'] == 1 and r['target_stance'] == 7)['exact_rate'])

    def test_fail_closed_bad_trajectory_or_feed(self):
        for field, value in [('before', 2), ('after', 9)]:
            run = unit_run()
            run['events'].loc[0, field] = value
            with self.assertRaises(ValueError):
                self.analyze(run)
        run = unit_run()
        run['events'].loc[1, 'agent_id'] = 'UNKNOWN_UNIT_AGENT'
        with self.assertRaises(ValueError):
            self.analyze(run)
        run = unit_run()
        run['feed'].loc[0, 'publication_ordinal'] = 4
        with self.assertRaises(ValueError):
            self.analyze(run)

    def test_neutral_start_and_baseline_formation(self):
        run = unit_run()
        run['initial_stances']['a'] = 4
        run['events'].loc[0, 'before'] = 4
        tables = self.analyze(run)
        self.assertEqual(tables['A2_event_exposure_numeric'][0]['exposure_class'], 'neutral_start')
        baseline = next(r for r in tables['A1_dominant_stance_formation']
                        if r['agent_id'] == 'b' and r['target_stance'] == 5)
        self.assertEqual(baseline['first_entry_round'], 0)
        self.assertEqual(baseline['leave_count'], 1)
        self.assertEqual(baseline['reentry_count'], 1)
        self.assertFalse(baseline['retained_continuously'])

    def test_cumulative_crossings_and_post_key_fallback(self):
        run = unit_run()
        run['feed']['post_id'] = None
        tables = self.analyze(run)
        row = next(r for r in tables['A1_cumulative_flow'] if r['round'] == 3 and r['stance'] == 3)
        self.assertEqual(row['cumulative_inflow'], 2)
        self.assertEqual(row['cumulative_outflow'], 2)
        self.assertEqual(row['cumulative_net_flow'], 0)
        self.assertEqual(tables['A2_event_exposure_numeric'][4]['post_key_method'],
                         'source_publication_compound')
        self.assertEqual(tables['A2_event_exposure_numeric'][4]['repeat_post_slots'], 1)

    def test_group_counts_ages_and_current_direction(self):
        events = self.analyze()['A2_event_exposure_numeric']
        self.assertEqual(events[0]['other_group_count'], 2)
        self.assertEqual(events[0]['other_group_share'], 1)
        self.assertEqual(events[0]['mean_post_age'], 1)
        self.assertEqual(events[2]['mean_post_age'], 1)
        self.assertEqual(events[4]['mean_post_age'], 2)
        self.assertEqual(events[4]['below_count'], 1)
        self.assertEqual(events[4]['prior_below_slots'], 1)

    def test_old_post_is_immutable_after_new_publication_and_nullable_reason(self):
        run = unit_run()
        # b publishes 5 at ordinal 3, but a actually reads b's older 3 post at 4.
        run['events'].loc[3, 'published'] = True
        run['events']['reason_changed'] = pd.Series([pd.NA, False, True, pd.NA, False, True], dtype='boolean')
        rows = self.analyze(run)['A2_event_exposure_numeric']
        self.assertEqual(rows[4]['feed_stance_3_count'], 1)
        self.assertIsNone(rows[0]['reason_changed'])
        self.assertIs(rows[1]['reason_changed'], False)
        self.assertIs(rows[2]['reason_changed'], True)
        run['feed'].loc[5, 'source_stance'] = 5
        with self.assertRaises(ValueError):
            self.analyze(run)

    def test_operational_classes_threshold_and_empty_feed(self):
        self.analyze()  # load/check module
        classify = self.mod._exposure_class
        self.assertEqual(classify(3, [1, 2, 7]), 'same_side_majority_2of3')
        self.assertEqual(classify(3, [5, 6, 3]), 'opposite_side_majority_2of3')
        self.assertEqual(classify(3, [1, 4, 7]), 'mixed')
        self.assertEqual(classify(4, [5, 5]), 'neutral_start')
        run = unit_run()
        run['feed'] = run['feed'].iloc[:0]
        out = self.analyze(run)
        self.assertTrue(all(r['exposure_class'] == 'no_feed' for r in out['A2_event_exposure_numeric']))
        self.assertTrue(all(r['exact_rate'] is None for r in out['A2_directional_update_rates']))

    def test_weighted_activation_repeats_actor_within_round(self):
        run = unit_run()
        run['feed'] = run['feed'].iloc[:0]
        run['events']['agent_id'] = ['a', 'a', 'a', 'b', 'a', 'b']
        run['events']['before'] = [3, 4, 3, 5, 5, 5]
        run['events']['after'] = [4, 3, 5, 5, 3, 5]
        out = self.analyze(run)
        matrix = pd.DataFrame(out['A1_round_transition_matrices'])
        self.assertEqual(matrix.groupby('round')['count'].sum().tolist(), [2, 2, 2])
        self.assertEqual(matrix.groupby('round')['n_unique_agents'].first().tolist(), [1, 2, 2])
        events = out['A2_event_exposure_numeric']
        self.assertEqual([r['activation_count'] for r in events], [1, 2, 3, 1, 4, 2])
        self.assertEqual([r['prior_activation_count'] for r in events], [0, 1, 2, 0, 3, 1])
        counts = pd.DataFrame(out['A1_net_stance_flows']).groupby('round')['population_count'].sum()
        self.assertEqual(counts.tolist(), [2, 2, 2])


if __name__ == '__main__':
    unittest.main()

"""UNIT-only numeric cases and explicit synthetic text sent only to controlled V output."""
import importlib.util
from pathlib import Path
import unittest
import pandas as pd

MODULE = Path(__file__).resolve().parents[1] / 'casebook.py'
CONTROLLED = Path('V:/Agent EX/Agent-EX-evidence/2026-11-01/ica-rq2-rq3-v1/tests-rq2')


def unit_events():
    return pd.DataFrame([dict(topic_key=f'UNIT{i%3}', matched_seed=i%2,
                             run_id=f'UNIT_RUN{i//10}', ordinal=i%10,
                             identity_a=f'A{i%2}', network_b=f'B{i%3}',
                             round=1, agent_id=f'UNIT_AGENT{i}', prior_stance=5,
                             after_stance=3 if i%2 else 5, feed_length=2,
                             feed_stance_3_count=2, feed_stance_5_count=0,
                             feed_mean=3.0, reason_changed=None if i%3 else True,
                             source_path='DO_NOT_COPY', before_reason='DO_NOT_COPY')
                         for i in range(180)])


class CasebookUnitTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mod = None
        if MODULE.exists():
            spec = importlib.util.spec_from_file_location('casebook', MODULE)
            cls.mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(cls.mod)

    def test_exact_size_determinism_no_raw_fields_and_pending_codes(self):
        self.assertIsNotNone(self.mod, 'casebook selection is not implemented')
        first = self.mod.select_candidates(unit_events())
        second = self.mod.select_candidates(unit_events().sample(frac=1, random_state=71))
        self.assertEqual(first, second)
        self.assertEqual(len(first['A3_candidate_cases']), 150)
        self.assertEqual(len({r['case_id'] for r in first['A3_candidate_cases']}), 150)
        self.assertNotIn('DO_NOT_COPY', str(first))
        self.assertTrue(all(r['coder_assessment'] == 'pending_human_review'
                            for r in first['A3_mechanism_evidence_matrix']))

    def test_missing_sidecars_and_selected_only_adapter_reads(self):
        self.assertIsNotNone(self.mod, 'casebook selection is not implemented')
        rows = self.mod.select_candidates(unit_events(), n=3)['A3_candidate_cases']
        seen = []
        def adapter(run_id, ordinal):
            seen.append((run_id, ordinal))
            return {} if len(seen) > 1 else dict(before_reason='UNIT EXACT OLD',
                                                 after_reason='UNIT EXACT NEW',
                                                 feed=[dict(text='UNIT EXACT FEED')])
        out = CONTROLLED / 'unit-casebook-output'
        path = self.mod.write_private_casebook(rows, adapter, out)
        text = path.read_text(encoding='utf-8')
        self.assertEqual(len(seen), 3)
        self.assertIn('UNIT EXACT OLD', text)
        self.assertIn('UNIT EXACT NEW', text)
        self.assertIn('UNIT EXACT FEED', text)
        self.assertIn('MISSING_NOT_RECOVERED', text)

    def test_forbidden_destination_and_duplicate_event_fail(self):
        self.assertIsNotNone(self.mod, 'casebook selection is not implemented')
        with self.assertRaises(ValueError):
            self.mod.write_private_casebook([], {}, MODULE.parent)
        rows = unit_events()
        rows.loc[1, ['run_id', 'ordinal']] = rows.loc[0, ['run_id', 'ordinal']]
        with self.assertRaises(ValueError):
            self.mod.select_candidates(rows)

    def test_many_strata_and_insufficient_distinct_events(self):
        self.assertIsNotNone(self.mod)
        rows = unit_events()
        rows['topic_key'] = [f'UNIT_TOPIC_{i}' for i in range(len(rows))]
        first = self.mod.select_candidates(rows, n=10)
        second = self.mod.select_candidates(rows.sample(frac=1, random_state=5), n=10)
        self.assertEqual(first, second)
        self.assertEqual(len(first['A3_candidate_cases']), 10)
        self.assertEqual(len(self.mod.select_candidates(rows.iloc[:2])['A3_candidate_cases']), 2)

    def test_known_empty_feed_is_not_missing_text(self):
        row=dict(case_id='UNIT_EMPTY',run_id='UNIT',ordinal=0,feed_length=0)
        sidecar={('UNIT',0):dict(before_reason='UNIT_OLD',after_reason='UNIT_NEW',feed=[])}
        path=self.mod.write_private_casebook([row],sidecar,CONTROLLED/'unit-known-empty-feed')
        text=path.read_text(encoding='utf-8')
        self.assertIn('NO_SELECTED_FEED',text)
        self.assertNotIn('MISSING_NOT_RECOVERED',text)


if __name__ == '__main__':
    unittest.main()

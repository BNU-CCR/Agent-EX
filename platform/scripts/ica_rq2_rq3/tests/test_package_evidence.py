"""Tiny UNIT packaging fixtures, not scientific findings; all outputs on V."""
import importlib.util
import json
from pathlib import Path
import unittest
import zipfile
import sys

MODULE = Path(__file__).resolve().parents[1] / 'package_evidence.py'
UNIT_ROOT = Path('V:/Agent EX/Agent-EX-evidence/2026-11-01/ica-rq2-rq3-v1/tests-rq2/package-unit')


class PackageUnitTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mod = None
        if MODULE.exists():
            spec = importlib.util.spec_from_file_location('package_evidence', MODULE)
            cls.mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(cls.mod)

    def test_zip_member_hash_crc_restore_and_source_unchanged(self):
        self.assertIsNotNone(self.mod, 'packager is not implemented')
        UNIT_ROOT.mkdir(parents=True, exist_ok=True)
        src = UNIT_ROOT / 'UNIT_numeric.csv'
        src.write_bytes(b'UNIT_VALUE\n7\n')
        before = self.mod.sha256(src)
        result = self.mod.write_verified_zip(UNIT_ROOT/'UNIT_package.zip', {'tables/UNIT_numeric.csv': src},
                                             {'METHODS.md': b'UNIT ONLY\n'})
        self.assertEqual(result['members_verified'], 3)
        self.assertTrue(result['crc_ok'])
        self.assertTrue(result['small_csv_restored_exactly'])
        self.assertEqual(before, self.mod.sha256(src))
        with zipfile.ZipFile(UNIT_ROOT/'UNIT_package.zip') as archive:
            self.assertIn('SHA256SUMS', archive.namelist())

    def test_gate_requires_complete_exact_cohorts_and_event_counts(self):
        self.assertIsNotNone(self.mod, 'packager is not implemented')
        for data in [{}, {'completed_horizon_trajectories':102,'unique_network_events':1890000,
                         'sources':[],'model_requests':0}]:
            with self.assertRaises(ValueError):
                self.mod.validate_aggregate(data)
        sources=[]
        for topic,horizon,seeds in [('retirement',30,range(20261201,20261211)),
                                    ('retirement',60,range(20261201,20261204)),
                                    ('gm-market-support',60,range(20261201,20261203)),
                                    ('genai-net-job-loss',60,range(20261201,20261203))]:
            for seed in seeds:
                for a in range(2):
                    for b in range(3):
                        sources.append(dict(meta=dict(topic_key=topic,matched_seed=seed,
                            cell_id=f'SIS-A{a}-B{b}',horizon=horizon),n_agents=500,n_events=500*horizon,
                            **{field:True for field in ('original_records_replayed','all_events_successful',
                            'before_after_chain_validated','population_flow_conserved','historical_public_feed_validated')}))
        synthetic_unit=dict(completed_horizon_trajectories=102,unique_network_events=1890000,
                            sources=sources,model_requests=0)
        self.assertTrue(self.mod.validate_aggregate(synthetic_unit))

    def test_review_explicit_raw_and_event_exclusions(self):
        self.assertIsNotNone(self.mod, 'packager is not implemented')
        for name in ['A2_event_exposure_numeric.csv.gz', 'private-reasons.jsonl.gz',
                     'initial.json', 'run.sqlite3', 'A3_text_evidence_casebook.md']:
            self.assertFalse(self.mod.review_allowed(Path(name)), name)
        self.assertTrue(self.mod.review_allowed(Path('A1_cumulative_flow.csv.gz')))

    def test_canonical_sidecars_access_selected_events_only(self):
        self.assertIsNotNone(self.mod, 'packager is not implemented')
        import gzip
        folder = UNIT_ROOT/'UNIT_canonical'
        folder.mkdir(parents=True, exist_ok=True)
        with gzip.open(folder/'private-reasons.jsonl.gz', 'wt', encoding='utf-8') as stream:
            for ordinal in range(5):
                stream.write(json.dumps(dict(ordinal=ordinal,before_reason='UNIT_PRIVATE',after_reason=None,feed=[]))+'\n')
        selected = [dict(run_id='UNIT_RUN',ordinal=3)]
        sidecars = self.mod.selected_sidecars(selected, {'UNIT_RUN': folder})
        self.assertEqual(set(sidecars), {('UNIT_RUN',3)})
        self.assertEqual(sidecars[('UNIT_RUN',3)]['before_reason'], 'UNIT_PRIVATE')

    def test_stream_pool_keeps_longest_horizon_without_prefix_duplicate(self):
        self.assertIsNotNone(self.mod)
        sys.path.insert(0,str(MODULE.parent))
        import casebook
        import pandas as pd
        path=UNIT_ROOT/'UNIT_candidate_events.csv.gz'
        UNIT_ROOT.mkdir(parents=True,exist_ok=True)
        rows=[]
        for horizon in (30,60):
            for ordinal in range(6):
                rows.append(dict(topic_key='UNIT',matched_seed=7,cell_id='SIS-A0-B1',
                                 run_id='UNIT_RUN',ordinal=ordinal,horizon=horizon,identity_a='A0',network_b='B1',
                                 prior_stance=5,after_stance=3,feed_length=1,
                                 feed_stance_3_count=1,reason_changed=False))
        pd.DataFrame(rows).to_csv(path,index=False,compression='gzip')
        pool=self.mod._candidate_pool(path,{('UNIT',7,'SIS-A0-B1'):60},n=3)
        self.assertTrue((pool.horizon==60).all())
        self.assertFalse(pool.duplicated(['run_id','ordinal']).any())
        self.assertEqual(len(casebook.select_candidates(pool,n=3)['A3_candidate_cases']),3)

    def test_declared_source_hashes_fail_closed(self):
        self.assertIsNotNone(self.mod)
        path=UNIT_ROOT/'UNIT_hashcheck.csv'
        UNIT_ROOT.mkdir(parents=True,exist_ok=True)
        path.write_bytes(b'UNIT_DATA\n')
        self.assertTrue(hasattr(self.mod,'verify_declared_inputs'),'source input verification missing')
        self.mod.verify_declared_inputs({path:self.mod.sha256(path)})
        with self.assertRaises(ValueError):
            self.mod.verify_declared_inputs({path:'0'*64})


if __name__ == '__main__':
    unittest.main()

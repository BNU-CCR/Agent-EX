import unittest
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from verify_numeric_results import recompute


class IndependentArithmeticTests(unittest.TestCase):
    def fixture(self):
        return dict(node_ids=['a','b'],groups={'a':'Blue','b':'Green'},edges=[['a','b']],
            initial_stances={'a':5,'b':3},initial_public={'a':5,'b':3},
            meta={'horizon':1}, snapshots=[{'next_event_ordinal':2,'private':{'a':4,'b':3},'public':{'a':3,'b':3}}],
            events=[dict(ordinal=0,agent_id='a',before=5,after=3,published=True),
                    dict(ordinal=1,agent_id='a',before=3,after=4,published=False)],
            feed=[dict(ordinal=0,receiver_agent_id='a',source_agent_id='b',source_stance=3,publication_ordinal=None,post_id='r0b',display_slot=0)])

    def test_serial_repeated_activation_flow(self):
        result=recompute(self.fixture())
        self.assertEqual(result['transitions'][(1,5,3)],1)
        self.assertEqual(result['transitions'][(1,3,4)],1)
        self.assertEqual(result['rounds'][1]['counts'],{1:0,2:0,3:1,4:1,5:0,6:0,7:0})
        self.assertEqual(result['rounds'][1]['variance'],.25)
        self.assertEqual(result['directional'][(5,3)],{'n_opportunities':1,'n_exact_i_to_j':1,'n_toward_target':1})

    def test_future_feed_rejected(self):
        run=self.fixture();run['feed'][0]['publication_ordinal']=1
        with self.assertRaisesRegex(ValueError,'publication'):recompute(run)

    def test_wrong_original_snapshot_rejected(self):
        run=self.fixture();run['snapshots'][0]['private']['a']=7
        with self.assertRaisesRegex(ValueError,'snapshot'):recompute(run)


if __name__=='__main__':unittest.main()

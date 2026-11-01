"""Small numerical unit fixtures only; not simulated research evidence."""
import importlib.util
from pathlib import Path
import unittest

P = Path(__file__).resolve().parents[1] / "p0_context.py"
spec = importlib.util.spec_from_file_location("p0_context", P)
m = importlib.util.module_from_spec(spec)
if P.exists():
    spec.loader.exec_module(m)


class P0ContextTests(unittest.TestCase):
    def test_api_exists(self):
        self.assertTrue(callable(getattr(m, "summarize_numeric", None)))

    def test_actual_counts_not_simplified_fractions(self):
        rows = [dict(topic_key="unit", initial_stance=5, feed_condition="low",
                     source_labels_visible=False, output_stance=y, pilot=False,
                     reverse_proposition=False, reverse_mapping=False,
                     reason_index=0, draw_seed=d) for d,y in enumerate([3,3,5])]
        result = m.summarize_numeric(rows)
        self.assertEqual(len(result), 1)
        r = result[0]
        self.assertEqual(r["n_cases"], 3)
        self.assertEqual(r["n_changed"], 2)
        self.assertEqual(r["changed_rate"], 2/3)
        self.assertEqual(r["n_5_to_3"], 2)
        self.assertEqual(r["denominator_5_to_3"], 3)
        self.assertEqual(sum(r[f"output_count_{k}"] for k in range(1,8)), 3)

    def test_visibility_and_feed_are_not_pooled(self):
        rows = [dict(topic_key="unit", initial_stance=3, feed_condition=f,
                     source_labels_visible=v, output_stance=3, pilot=False,
                     reverse_proposition=False, reverse_mapping=False,
                     reason_index=0, draw_seed=0) for f,v in [("none",False),("low",False),("low",True)]]
        result = m.summarize_numeric(rows)
        self.assertEqual(len(result), 3)
        self.assertTrue(all(r["denominator_5_to_3"] == 0 and r["rate_5_to_3"] is None for r in result))

    def test_missing_field_is_not_inferred(self):
        with self.assertRaises(ValueError):
            m.summarize_numeric([dict(topic_key="unit", initial_stance=3,
                                      feed_condition="none", output_stance=3)])

    def test_json_digest_is_stable_and_not_text_export(self):
        self.assertEqual(m.encoded({"b":1,"a":2}), b'{"a":2,"b":1}')

    def test_usage_projection_ignores_provider_detail_not_token_counts(self):
        actual = dict(prompt_tokens=2, completion_tokens=3, total_tokens=5,
                      prompt_tokens_details=dict(cached_tokens=0))
        self.assertEqual(m.numeric_usage(actual), dict(prompt_tokens=2, completion_tokens=3, total_tokens=5))
        with self.assertRaises(ValueError):
            m.numeric_usage(dict(prompt_tokens=2, completion_tokens=3, total_tokens=6))


if __name__ == "__main__":
    unittest.main()

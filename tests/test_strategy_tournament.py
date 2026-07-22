import copy
import json
import tempfile
import unittest
from pathlib import Path

from scripts.build_strategy_tournament import build, canonical_hash
from scripts.plan_strategy_tournament import build_plan


class StrategyTournamentTests(unittest.TestCase):
    def test_registry_has_100_materially_distinct_candidates(self):
        registry, screening, matrix = build()
        self.assertEqual(len(registry["candidates"]), 100)
        self.assertEqual(len({row["mechanism_fingerprint"] for row in registry["candidates"]}), 100)
        self.assertEqual(len(screening["frozen_stratified_leaf_sample"]), 8)
        self.assertEqual(screening["maximum_parallel_searches"], 1)
        self.assertEqual(matrix["covered_frontier_targets"], ["s-r0-6", "s-r1-5", "s-r1-8"])

    def test_pending_candidate_cannot_enter_screen(self):
        registry, _, _ = build()
        pending = [row for row in registry["candidates"] if row["validation_status"] == "pending"]
        self.assertEqual(len(pending), 98)
        self.assertTrue(all(row["screen_status"] == "blocked_pending_semantic_gate" for row in pending))

    def test_registry_hash_detects_mutation(self):
        registry, _, _ = build()
        altered = copy.deepcopy(registry)
        recorded = altered.pop("registry_payload_sha256")
        altered["candidates"][0]["variant"] = "renamed-without-new-mechanism"
        self.assertNotEqual(canonical_hash(altered), recorded)

    def test_plan_is_serial_and_gates_all_unvalidated_candidates(self):
        plan = build_plan()
        self.assertEqual(plan["maximum_parallel_searches"], 1)
        self.assertEqual(len(plan["active_searches"]), 1)
        self.assertEqual(plan["admitted_screen_methods"], [])
        self.assertEqual(len(plan["next_semantic_validation_queue"]), 98)
        self.assertEqual(len(plan["open_leaf_assignments"]), 44)


if __name__ == "__main__":
    unittest.main()

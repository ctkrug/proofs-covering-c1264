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
        self.assertEqual(len(matrix["covered_frontier_targets"]), 15)

    def test_pending_candidate_cannot_enter_screen(self):
        registry, _, _ = build()
        pending = [row for row in registry["candidates"] if row["validation_status"] == "pending"]
        self.assertEqual(len(pending), 91)
        self.assertTrue(all(row["screen_status"] == "blocked_pending_semantic_gate" for row in pending))

    def test_registry_hash_detects_mutation(self):
        registry, _, _ = build()
        altered = copy.deepcopy(registry)
        recorded = altered.pop("registry_payload_sha256")
        altered["candidates"][0]["variant"] = "renamed-without-new-mechanism"
        self.assertNotEqual(canonical_hash(altered), recorded)

    def test_plan_preserves_serial_live_host_and_uses_family_champions(self):
        plan = build_plan()
        self.assertEqual(plan["maximum_parallel_searches"], 1)
        self.assertEqual(len(plan["active_searches"]), 1)
        self.assertEqual(plan["separate_local_workstation_constructive_searches"], 2)
        self.assertEqual(len(plan["family_champions"]), 10)
        self.assertLess(len(plan["next_semantic_validation_queue"]), 10)
        self.assertIn("constructive_local_search-04", plan["admitted_screen_methods"])
        self.assertEqual(len(plan["open_leaf_assignments"]), 32)


if __name__ == "__main__":
    unittest.main()

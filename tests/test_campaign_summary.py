from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


summary = load("summarize_link_campaign", ROOT / "scripts" / "summarize_link_campaign.py")


class CampaignSummaryTests(unittest.TestCase):
    def test_current_checkpoint_is_fully_bound(self) -> None:
        value = summary.build()
        self.assertEqual(value["catalog"]["distinct_link_orbits"], 4)
        self.assertEqual(value["validated_external_proof_receipts"], 189)
        self.assertEqual(value["open_secondary_count"], 14)
        self.assertEqual(value["open_tertiary_count"], 33)
        self.assertEqual(value["open_frontier_count"], 47)
        self.assertEqual(value["secondary_roots"]["0"]["validated_unsat"], 32)
        self.assertEqual(value["secondary_roots"]["1"]["validated_unsat"], 60)


if __name__ == "__main__":
    unittest.main()

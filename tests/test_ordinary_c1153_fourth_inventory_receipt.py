from __future__ import annotations

import json
import unittest
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RECEIPT = ROOT / "evidence/ordinary-c1153-fourth-inventory-20260723-v4/audit.json"


class OrdinaryC1153FourthInventoryReceiptTests(unittest.TestCase):
    def test_frozen_inventory_receipt(self) -> None:
        value = json.loads(RECEIPT.read_text())
        self.assertEqual(value["status"], "VALID")
        self.assertEqual(value["reconstruction"]["top_level"]["count"], 5)
        self.assertEqual(value["reconstruction"]["third_level"]["count"], 42)
        self.assertEqual(value["reconstruction"]["fourth_level"]["parent_count"], 13)
        self.assertEqual(value["reconstruction"]["fourth_level"]["branches"], 790)
        self.assertEqual(value["reconstruction"]["fourth_level"]["eligible_blocks"], 5246)
        self.assertEqual(
            Counter(row["status"] for row in value["inventory"]),
            Counter({"UNSAT_REPLAYED": 406, "UNMEASURED": 352, "FIXED_CAP_TIMEOUT": 32}),
        )
        self.assertEqual(value["accounting"]["open_branches"], 384)
        self.assertTrue(value["negative_control"]["hash_mismatch_detected"])
        self.assertTrue(value["negative_control"]["proof_replay_rejected"])


if __name__ == "__main__":
    unittest.main()

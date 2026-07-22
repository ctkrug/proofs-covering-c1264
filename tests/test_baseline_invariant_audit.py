from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


producer = load("audit_baseline_invariants", ROOT / "scripts" / "audit_baseline_invariants.py")
checker = load("verify_baseline_invariants", ROOT / "checkers" / "verify_baseline_invariants.py")


class BaselineInvariantAuditTests(unittest.TestCase):
    def test_producer_and_independent_checker_agree(self) -> None:
        witness = ROOT / "sources" / "ljcr-c1264-41.txt"
        result = producer.audit(witness)
        self.assertEqual(result["status"], "valid-baseline-audit")
        consequences = result["hypothetical_40_consequences"]
        self.assertEqual(consequences["matching_count"], 10_395)
        self.assertEqual(consequences["block_r_class_counts"], {"0": 64, "1": 480, "2": 360, "3": 20})
        self.assertFalse(result["negative_control"]["passes_cover_check"])

        with tempfile.TemporaryDirectory() as raw:
            result_path = Path(raw) / "result.json"
            result_path.write_text(json.dumps(result), encoding="utf-8")
            receipt = checker.verify(result_path, witness)
        self.assertEqual(receipt["status"], "valid-independent-check")
        self.assertTrue(all(receipt["checks"].values()))

    def test_root_split_covers_every_feasible_profile(self) -> None:
        profiles = producer.degree_profiles()
        self.assertEqual(len(profiles), 221)
        self.assertTrue(all(n0 > 0 or n1 > 0 for n0, n1, _n2, _n3 in profiles))


if __name__ == "__main__":
    unittest.main()

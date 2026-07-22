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


auditor = load("audit_exhaustive_link_phase", ROOT / "checkers" / "audit_exhaustive_link_phase.py")
indexer = load("build_link_classification_receipt_index", ROOT / "scripts" / "build_link_classification_receipt_index.py")


class ExhaustiveLinkPhaseTests(unittest.TestCase):
    def test_exact_domain_symmetry_and_partition_audit(self) -> None:
        result = auditor.audit("artifacts/portfolio/frontier-manifest-26of47-seven-orbit-snapshot.json")
        self.assertEqual(result["status"], "valid")
        self.assertEqual(result["classification_domain"]["candidate_primary_variables"], 462)
        self.assertEqual(result["symmetry"]["actions_independently_enumerated"], 3840)
        self.assertEqual(result["partition_coverage"]["active_frontier_nodes"], 47)
        self.assertFalse(result["catalogue"]["exhaustive"])

    def test_receipt_index_reconciles_20_to_26_without_counting_orbits(self) -> None:
        result = indexer.build()
        self.assertEqual(result["counts"]["durable_preexisting_closures"], 20)
        self.assertEqual(result["counts"]["promoted_new_closures"], 6)
        self.assertEqual(result["counts"]["promoted_global_closures"], 26)
        self.assertEqual(result["counts"]["validated_new_orbits_not_closures"], 2)
        self.assertEqual(result["duplicate_retry_nodes"]["nodes"], ["t-7", "t-8", "t-9"])
        self.assertEqual(len(result["duplicate_retry_nodes"]["receipts"]), 3)


if __name__ == "__main__":
    unittest.main()

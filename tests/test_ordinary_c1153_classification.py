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


builder = load("build_ordinary_c1153", ROOT / "scripts/build_ordinary_c1153_classification_gate.py")
verifier = load("verify_ordinary_c1153", ROOT / "checkers/verify_ordinary_c1153_classification.py")


class OrdinaryC1153ClassificationTests(unittest.TestCase):
    def test_cardinality_recurrence_agrees(self) -> None:
        left, top_left, _ = builder.exact_count_twenty(list(range(1, 463)), 462)
        right, top_right = verifier.independent_cardinality(list(range(1, 463)), 462)
        self.assertEqual(top_left, top_right)
        self.assertEqual(left, right)

    def test_frozen_first_gate(self) -> None:
        manifest = ROOT / "artifacts/classification/ordinary-c1153-v1/manifest.json"
        if not manifest.exists():
            self.skipTest("first gate not built")
        result = verifier.verify(manifest)
        self.assertEqual(result["status"], "VALID_FIRST_GATE")
        self.assertEqual(result["branch_leaf_count"], 5)
        self.assertFalse(result["classification_complete"])


if __name__ == "__main__":
    unittest.main()

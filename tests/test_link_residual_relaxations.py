from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
SPEC = importlib.util.spec_from_file_location(
    "profile_link_residual_relaxations", ROOT / "scripts" / "profile_link_residual_relaxations.py",
)
module = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(module)


class LinkResidualRelaxationTests(unittest.TestCase):
    def test_metrics_accept_known_41_cover_but_not_as_40_cover(self) -> None:
        path = ROOT / "sources" / "ljcr-c1264-41.txt"
        blocks = [tuple(int(value) - 1 for value in line.split())
                  for line in path.read_text().splitlines() if line.strip()]
        metrics = module.candidate_metrics(blocks)
        self.assertEqual(metrics["uncovered_count"], 0)
        self.assertEqual(metrics["block_count"], 41)
        self.assertFalse(metrics["is_valid_40_cover"])


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "extract_link_residual_semantic_core", ROOT / "scripts" / "extract_link_residual_semantic_core.py",
)
module = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(module)


class LinkResidualSemanticCoreTests(unittest.TestCase):
    def test_fifth_orbit_group_partition_matches_full_residual(self):
        groups, top = module.build_groups(
            ROOT / "artifacts" / "discoveries" / "link-orbit-s-r1-3" / "witness.txt",
        )
        self.assertEqual(230, sum(row["kind"] == "coverage" for row in groups))
        self.assertEqual(55, sum(row["kind"] == "pair_equality" for row in groups))
        self.assertEqual(285, len(groups))
        self.assertEqual(72754, top)


if __name__ == "__main__":
    unittest.main()

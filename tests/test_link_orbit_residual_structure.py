from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
SPEC = importlib.util.spec_from_file_location(
    "profile_link_orbit_residual_structure", ROOT / "scripts" / "profile_link_orbit_residual_structure.py",
)
module = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(module)


class LinkOrbitResidualStructureTests(unittest.TestCase):
    def test_fifth_orbit_fills_the_two_aligned_edge_signature(self):
        value = module.profile(ROOT / "artifacts" / "discoveries" / "link-orbit-catalog-5.json")
        self.assertEqual(5, len(value["orbits"]))
        self.assertEqual([0, 1, 2, 3, 3], sorted(row["low_pairs_aligned_with_forced_matching"] for row in value["orbits"]))
        self.assertEqual(2, value["orbits"][-1]["low_pairs_aligned_with_forced_matching"])
        self.assertEqual([0, 1, 2, 3], value["matching_alignment_branch"]["observed_values"])
        self.assertEqual(1776, value["matching_alignment_branch"]["orbit_images_exhaustively_checked"])


if __name__ == "__main__":
    unittest.main()

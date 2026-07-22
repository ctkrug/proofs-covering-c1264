from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
spec = importlib.util.spec_from_file_location("hard_tail", ROOT / "scripts" / "analyze_nine_orbit_timeout_hard_tail.py")
assert spec and spec.loader
hard_tail = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hard_tail)


class NineOrbitHardTailTests(unittest.TestCase):
    def test_exact_timeout_partition_and_discriminator(self) -> None:
        result = hard_tail.build()
        self.assertEqual(result["hard_tail_size"], 12)
        self.assertEqual(result["summary"]["by_kind"], {"secondary": 10, "tertiary": 2})
        self.assertEqual(result["summary"]["measured_under_active_nine_orbit_blocker"], 0)
        self.assertEqual(result["selected_discriminator"]["ordered_nodes"], ["s-r0-1", "s-r1-15", "t-10"])
        self.assertEqual(result["selected_discriminator"]["status"], "predeclared_not_launched")


if __name__ == "__main__":
    unittest.main()

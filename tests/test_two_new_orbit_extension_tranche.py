from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("extension", ROOT / "scripts" / "build_two_new_orbit_extension_tranche.py")
assert spec and spec.loader
extension = importlib.util.module_from_spec(spec)
spec.loader.exec_module(extension)


class TwoNewOrbitExtensionTests(unittest.TestCase):
    def test_exact_two_orbits_and_caps(self) -> None:
        manifest = extension.build()
        self.assertEqual([row["id"] for row in manifest["ordered_units"]], ["orbit-8-t-16", "orbit-9-t-17"])
        self.assertEqual([row["seconds_cap"] for row in manifest["ordered_units"]], [300, 300])
        self.assertEqual(manifest["maximum_units"], 2)


if __name__ == "__main__":
    unittest.main()

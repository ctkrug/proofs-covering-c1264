from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "checkers"))
KNOWN = ROOT / "artifacts" / "controls" / "c1153-at-most-20-seqcounter-fix-first-exact-degrees-300s" / "witness.txt"
SECOND = ROOT / "artifacts" / "pilot" / "link-orbit-second-root-2-60s" / "witness.txt"


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


producer = load("build_link_orbit_catalog", ROOT / "scripts" / "build_link_orbit_catalog.py")
auditor = load("audit_link_orbit_catalog", ROOT / "checkers" / "audit_link_orbit_catalog.py")


class LinkOrbitCatalogTests(unittest.TestCase):
    def test_two_orbit_catalog_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            directory = Path(raw)
            blocking = directory / "blocking.cnf"
            result = producer.build([KNOWN, SECOND], blocking)
            catalog = directory / "catalog.json"
            catalog.write_text(json.dumps(result))
            checked = auditor.audit(catalog, blocking)
        self.assertEqual(checked["status"], "valid")
        self.assertEqual(checked["orbit_count"], 2)
        self.assertEqual(checked["blocked_link_images"], 336)

    def test_duplicate_orbit_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            with self.assertRaisesRegex(ValueError, "duplicates"):
                producer.build([KNOWN, KNOWN], Path(raw) / "blocking.cnf")


if __name__ == "__main__":
    unittest.main()

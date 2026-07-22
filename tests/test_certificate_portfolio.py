import copy
import json
import tempfile
import unittest
from pathlib import Path

from checkers.verify_certificate_portfolio import ROOT, verify
from scripts.build_certificate_portfolio import build


class CertificatePortfolioTests(unittest.TestCase):
    def test_initial_manifest_covers_exact_frontier_and_verifies(self):
        manifest = build()
        self.assertEqual(manifest["counts"], {"total": 47, "closed": 0, "open": 47})
        self.assertEqual(len(manifest["nodes"]), 47)
        self.assertEqual(sum(bool(row["assigned_methods"]) for row in manifest["nodes"]), 20)
        with tempfile.NamedTemporaryFile("w", suffix=".json", dir=ROOT, delete=False) as handle:
            json.dump(manifest, handle)
            path = Path(handle.name)
        try:
            verify(path)
        finally:
            path.unlink()

    def test_checker_rejects_uncertified_closed_node(self):
        manifest = build()
        broken = copy.deepcopy(manifest)
        broken["nodes"][0]["final_coverage_status"] = "closed_unsat"
        broken["counts"] = {"total": 47, "closed": 1, "open": 46}
        with tempfile.NamedTemporaryFile("w", suffix=".json", dir=ROOT, delete=False) as handle:
            json.dump(broken, handle)
            path = Path(handle.name)
        try:
            with self.assertRaises(AssertionError):
                verify(path)
        finally:
            path.unlink()


if __name__ == "__main__":
    unittest.main()

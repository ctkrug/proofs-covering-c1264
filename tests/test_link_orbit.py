from __future__ import annotations

import copy
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "artifacts" / "controls" / "c1153-at-most-20-seqcounter-fix-first-exact-degrees-300s" / "witness.txt"


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


producer = load("analyze_link_orbit", ROOT / "scripts" / "analyze_link_orbit.py")
auditor = load("audit_link_orbit", ROOT / "checkers" / "audit_link_orbit.py")


class LinkOrbitTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.result = producer.analyze(SOURCE)

    def test_exact_group_and_orbit_stabilizer(self) -> None:
        self.assertEqual(self.result["transformations_checked"], 3840)
        self.assertEqual(self.result["orbit_size"] * self.result["stabilizer_order"], 3840)
        self.assertIn("does not count or exhaust", self.result["claim_limit"])

    def test_independent_auditor_accepts(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            result = Path(raw) / "result.json"
            result.write_text(json.dumps(self.result))
            checked = auditor.audit(result, SOURCE)
        self.assertEqual(checked["status"], "valid")
        self.assertEqual(checked["orbit_size"], self.result["orbit_size"])

    def test_independent_auditor_rejects_false_canonical_key(self) -> None:
        altered = copy.deepcopy(self.result)
        altered["canonical_blocks"] = altered["canonical_blocks"][1:]
        with tempfile.TemporaryDirectory() as raw:
            result = Path(raw) / "result.json"
            result.write_text(json.dumps(altered))
            with self.assertRaisesRegex(ValueError, "canonical representative mismatch"):
                auditor.audit(result, SOURCE)

    def test_exact_orbit_blocklist_is_independently_rebuilt(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            blocking = Path(raw) / "orbit-blocking.cnf"
            result_payload = producer.analyze(SOURCE, blocking)
            result = Path(raw) / "result.json"
            result.write_text(json.dumps(result_payload))
            checked = auditor.audit(result, SOURCE, blocking)
        self.assertEqual(checked["orbit_blocking_cnf"]["clauses"], result_payload["orbit_size"])
        self.assertEqual(result_payload["orbit_blocking_cnf"]["literals_per_clause"], 20)


if __name__ == "__main__":
    unittest.main()

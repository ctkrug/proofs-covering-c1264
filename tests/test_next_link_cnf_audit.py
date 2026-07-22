from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RESULT = ROOT / "artifacts" / "pilot" / "link-orbit-third-root-2-60s" / "result.json"
BLOCKING = ROOT / "artifacts" / "pilot" / "link-orbit-catalog-3-blocking.cnf"


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


auditor = load("audit_next_link_cnf", ROOT / "checkers" / "audit_next_link_cnf.py")
finder = load("find_next_link_orbit_for_audit", ROOT / "scripts" / "find_next_link_orbit.py")


class NextLinkCnfAuditTests(unittest.TestCase):
    def test_exact_reconstruction_accepts(self) -> None:
        value = auditor.audit(RESULT)
        self.assertEqual(value["status"], "valid")
        self.assertEqual(value["root_index"], 2)

    def test_false_root_is_rejected(self) -> None:
        altered = copy.deepcopy(json.loads(RESULT.read_text()))
        altered["root_partition"]["canonical_block"] = [1, 2, 4, 6, 8]
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "result.json"
            path.write_text(json.dumps(altered))
            with self.assertRaisesRegex(ValueError, "wrong type"):
                auditor.audit(path)

    def test_exact_tertiary_reconstruction_accepts(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            output = Path(raw)
            cnf, _, ranges, _, root = finder.build(BLOCKING, 0, 0, 3)
            cnf_path = output / "instance.cnf"
            cnf.to_file(str(cnf_path))
            result_path = output / "result.json"
            result_path.write_text(json.dumps({
                "cnf": {"path": str(cnf_path), "sha256": hashlib.sha256(cnf_path.read_bytes()).hexdigest()},
                "blocking_cnf": {"path": str(BLOCKING), "sha256": hashlib.sha256(BLOCKING.read_bytes()).hexdigest()},
                "root_partition": root,
                "auxiliary_ranges": ranges,
            }))
            value = auditor.audit(result_path)
            self.assertEqual(value["status"], "valid")
            self.assertGreater(value["tertiary_earlier_orbit_units"], 0)

    def test_exact_quaternary_reconstruction_accepts(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            output = Path(raw)
            cnf, _, ranges, _, root = finder.build(BLOCKING, 0, 0, 3, 2)
            cnf_path = output / "instance.cnf"
            cnf.to_file(str(cnf_path))
            result_path = output / "result.json"
            result_path.write_text(json.dumps({
                "cnf": {"path": str(cnf_path), "sha256": hashlib.sha256(cnf_path.read_bytes()).hexdigest()},
                "blocking_cnf": {"path": str(BLOCKING), "sha256": hashlib.sha256(BLOCKING.read_bytes()).hexdigest()},
                "root_partition": root,
                "auxiliary_ranges": ranges,
            }))
            value = auditor.audit(result_path)
            self.assertEqual(value["status"], "valid")
            self.assertGreater(value["quaternary_earlier_orbit_units"], 0)


if __name__ == "__main__":
    unittest.main()

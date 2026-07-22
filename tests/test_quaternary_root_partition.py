from __future__ import annotations

import copy
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "checkers"))


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


builder = load("build_quaternary_root_partition", ROOT / "scripts" / "build_quaternary_root_partition.py")
auditor = load("audit_quaternary_root_partition", ROOT / "checkers" / "audit_quaternary_root_partition.py")


class QuaternaryRootPartitionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.valid = builder.build(0, 0, 1)

    def assert_rejected(self, value: dict, pattern: str) -> None:
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "partition.json"
            path.write_text(json.dumps(value))
            with self.assertRaisesRegex(ValueError, pattern):
                auditor.audit(path)

    def test_independent_auditor_accepts_complete_partition(self) -> None:
        value = copy.deepcopy(self.valid)
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "partition.json"
            path.write_text(json.dumps(value))
            checked = auditor.audit(path)
        self.assertEqual(checked["status"], "valid")
        self.assertEqual(checked["covered_eligible_variables"], value["eligible_primary_variables"])
        self.assertEqual(checked["quaternary_root_count"], value["quaternary_root_count"])

    def test_independent_auditor_rejects_prefix_hash_mutation(self) -> None:
        value = copy.deepcopy(self.valid)
        value["roots"][1]["earlier_orbit_variables_sha256"] = "0" * 64
        self.assert_rejected(value, "prefix hash")

    def test_rejects_schema_status_and_index_mutations(self) -> None:
        mutations = [
            ("schema", lambda value: value.__setitem__("schema_version", 2), "schema"),
            ("status", lambda value: value.__setitem__("status", "valid"), "status"),
            ("root-negative", lambda value: value.__setitem__("primary_root_index", -1), "root index out of range"),
            ("root-wrong-type", lambda value: value.__setitem__("primary_root_index", 1), "root type"),
            ("secondary-negative", lambda value: value.__setitem__("secondary_index", -1), "secondary index out of range"),
            ("tertiary-large", lambda value: value.__setitem__("tertiary_index", 10_000), "tertiary index out of range"),
            ("bool-index", lambda value: value.__setitem__("secondary_index", True), "must be an integer"),
            ("row-index", lambda value: value["roots"][0].__setitem__("quaternary_index", -1), "out of range"),
        ]
        for name, mutate, pattern in mutations:
            with self.subTest(name=name):
                value = copy.deepcopy(self.valid)
                mutate(value)
                self.assert_rejected(value, pattern)

    def test_rejects_primary_canonical_mutation(self) -> None:
        value = copy.deepcopy(self.valid)
        value["primary_canonical_block"] = [1, 2, 3, 4, 6]
        self.assert_rejected(value, "root type")


if __name__ == "__main__":
    unittest.main()

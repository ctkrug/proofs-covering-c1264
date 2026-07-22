from __future__ import annotations

import copy
import importlib.util
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "build_active_sequential_tranche", ROOT / "scripts" / "build_active_sequential_tranche.py"
)
assert SPEC and SPEC.loader
builder = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(builder)


class ActiveSequentialTrancheTests(unittest.TestCase):
    def setUp(self) -> None:
        self.portfolio = json.loads((ROOT / builder.PORTFOLIO).read_text(encoding="utf-8"))
        self.manifest = builder.build()

    def test_exact_seven_orbit_job_resolves_before_execution(self) -> None:
        builder.validate(self.manifest, self.portfolio)
        self.assertEqual(self.manifest["run_id"], "sequential-unmeasured-frontier-12-v7-20260722")
        self.assertEqual(len(self.manifest["leaves"]), 12)

    def test_rejects_already_certified_node(self) -> None:
        broken = copy.deepcopy(self.manifest)
        closed = next(row for row in self.portfolio["nodes"] if row["final_coverage_status"] != "open")
        broken["leaves"][0]["id"] = closed["id"]
        with self.assertRaisesRegex(ValueError, "already-certified"):
            builder.validate(broken, self.portfolio)

    def test_rejects_superseded_blocker(self) -> None:
        broken = copy.deepcopy(self.manifest)
        broken["blocking_cnf"] = self.portfolio["predecessor_link_blocker"]["path"]
        with self.assertRaisesRegex(ValueError, "superseded blocker"):
            builder.validate(broken, self.portfolio)


if __name__ == "__main__":
    unittest.main()

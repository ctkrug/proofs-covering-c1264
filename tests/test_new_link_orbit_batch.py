from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "checkers"))
spec = importlib.util.spec_from_file_location("audit_new_link_orbit_batch", ROOT / "checkers" / "audit_new_link_orbit_batch.py")
assert spec and spec.loader
auditor = importlib.util.module_from_spec(spec)
spec.loader.exec_module(auditor)


class NewLinkOrbitBatchTests(unittest.TestCase):
    def test_two_review_witnesses_are_distinct_from_seven_orbit_catalog(self) -> None:
        result = auditor.audit(
            ROOT / "artifacts/discoveries/link-orbit-catalog-7.json",
            [
                ROOT / "artifacts/sequential-frontier-sweep/sequential-three-case-review-v7-20260722/t-16/sequential/result.json",
                ROOT / "artifacts/sequential-frontier-sweep/sequential-three-case-review-v7-20260722/t-17/sequential/result.json",
            ],
        )
        self.assertEqual(result["status"], "valid-distinct-new-link-orbits")
        self.assertEqual(result["candidate_count"], 2)
        self.assertEqual(
            {row["canonical_sha256"] for row in result["candidates"]},
            {
                "7291235f9679362212e69d3e7eb50dbcfc445bb1da66a14bd0d01135a56a7894",
                "a2b4fb1c04cc3944b697840bb50d5cd55d89348f539bf48d6c8cb8a1a5e953d1",
            },
        )


if __name__ == "__main__":
    unittest.main()

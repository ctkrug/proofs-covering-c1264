import copy
import importlib.util
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("three_case", ROOT / "scripts/build_three_case_review_tranche.py")
assert SPEC and SPEC.loader
builder = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(builder)


class ThreeCaseReviewTrancheTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.portfolio = json.loads((ROOT / builder.SNAPSHOT).read_text())
        cls.index = json.loads((ROOT / builder.INDEX).read_text())
        cls.manifest = builder.build(builder.SNAPSHOT, write_snapshot=False)

    def test_exact_manifest_is_disjoint_and_hash_bound(self):
        builder.validate(self.manifest, self.portfolio, self.index, builder.SNAPSHOT)
        self.assertEqual([row["id"] for row in self.manifest["leaves"]], ["t-16", "t-17", "s-r0-1"])
        self.assertEqual(self.manifest["seconds_per_run"], 60)

    def test_rejects_durable_certificate_overlap(self):
        broken = copy.deepcopy(self.manifest)
        broken["leaves"][0]["id"] = self.index["closed_node_ids"][0]
        with self.assertRaisesRegex(ValueError, "exact three-case order changed|overlaps durable"):
            builder.validate(broken, self.portfolio, self.index, builder.SNAPSHOT)

    def test_rejects_cap_or_blocker_change(self):
        for key, value, message in (("seconds_per_run", 61, "method or cap changed"),
                                    ("blocking_cnf", self.portfolio["predecessor_link_blocker"]["path"], "stale blocker")):
            broken = copy.deepcopy(self.manifest)
            broken[key] = value
            with self.assertRaisesRegex(ValueError, message):
                builder.validate(broken, self.portfolio, self.index, builder.SNAPSHOT)


if __name__ == "__main__":
    unittest.main()

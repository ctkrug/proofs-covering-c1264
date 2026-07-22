from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
spec = importlib.util.spec_from_file_location("route_switch", ROOT / "scripts" / "ingest_three_case_review_route_switch.py")
assert spec and spec.loader
route_switch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(route_switch)


class ThreeCaseRouteSwitchTests(unittest.TestCase):
    def test_ingestion_preserves_ledger_and_records_exact_outcomes(self) -> None:
        manifest = route_switch.ingest()
        self.assertEqual(manifest["counts"], {"total": 47, "closed": 32, "open": 15})
        nodes = {row["id"]: row for row in manifest["nodes"]}
        statuses = {
            node_id: next(row["status"] for row in nodes[node_id]["outcomes"] if row.get("run_id") == route_switch.RUN_ID)
            for node_id in ("t-16", "t-17", "s-r0-1")
        }
        self.assertEqual(statuses, {
            "t-16": "provisional_sat",
            "t-17": "provisional_sat",
            "s-r0-1": "unknown",
        })
        legacy = next(row for row in nodes["s-r1-3"]["outcomes"] if row.get("method") == "sequential")
        self.assertEqual(legacy["status"], "provisional_sat")
        self.assertEqual(legacy["canonical_link_sha256"], "b470049c5444b5f9bdd253d6e096e42e52e42c3512e545b43a4ad8f9346bb49c")


if __name__ == "__main__":
    unittest.main()

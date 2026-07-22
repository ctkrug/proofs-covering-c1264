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


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


producer = load("rebind_five_orbit_frontier", ROOT / "scripts" / "rebind_five_orbit_frontier.py")
auditor = load("audit_five_orbit_frontier", ROOT / "checkers" / "audit_five_orbit_frontier.py")


class FiveOrbitFrontierTests(unittest.TestCase):
    def test_rebind_preserves_honest_global_count_and_audits(self) -> None:
        value = producer.rebind(Path("artifacts/portfolio/frontier-manifest-v1.json"))
        self.assertEqual(value["counts"], {"total": 47, "closed": 20, "open": 27})
        self.assertEqual(value["blocker_monotonicity"]["added_clauses"], 160)
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "manifest.json"
            path.write_text(json.dumps(value))
            result = auditor.audit(path)
        self.assertEqual(result["status"], "valid")
        self.assertEqual(result["frontier_nodes"], 47)


if __name__ == "__main__":
    unittest.main()

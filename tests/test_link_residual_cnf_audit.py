from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


auditor = load("audit_link_residual_cnf", ROOT / "checkers" / "audit_link_residual_cnf.py")


class LinkResidualCnfAuditTests(unittest.TestCase):
    def test_reconstructs_both_known_link_residuals(self) -> None:
        paths = [
            ROOT / "artifacts" / "pilot" / "link-residual-first-300s" / "result.json",
            ROOT / "artifacts" / "pilot" / "link-residual-second-orbit-300s" / "result.json",
        ]
        values = [auditor.audit(path) for path in paths]
        self.assertTrue(all(value["status"] == "valid" for value in values))
        self.assertEqual({value["coverage_constraints"] for value in values}, {230})


if __name__ == "__main__":
    unittest.main()

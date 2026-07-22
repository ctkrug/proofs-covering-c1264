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


auditor = load("audit_ordinary_c1153_hard_split", ROOT / "checkers/audit_ordinary_c1153_hard_split.py")


class OrdinaryC1153HardSplitTests(unittest.TestCase):
    def test_exact_split(self) -> None:
        path = ROOT / "artifacts/classification/ordinary-c1153-v1/hard-split/manifest.json"
        if not path.exists():
            self.skipTest("hard split not built")
        result = auditor.audit()
        self.assertEqual(result["status"], "VALID")
        self.assertEqual(result["total_children"], 42)


if __name__ == "__main__":
    unittest.main()

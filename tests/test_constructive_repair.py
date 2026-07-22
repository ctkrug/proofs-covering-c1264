from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


runner = load("run_constructive_repair", ROOT / "scripts" / "run_constructive_repair.py")
auditor = load("audit_constructive_repair", ROOT / "checkers" / "audit_constructive_repair.py")


class ConstructiveRepairTests(unittest.TestCase):
    def test_published_cover_deletions_start_close(self) -> None:
        warm = runner.read_blocks(ROOT / "sources" / "ljcr-c1264-41.txt")
        best = 495
        for removed in warm:
            selected = set(warm)
            selected.remove(removed)
            quad, points, pairs = runner.counts(selected)
            best = min(best, runner.metrics(quad, points, pairs)["uncovered_quadruples"])
        self.assertEqual(best, 7)

    def test_short_run_is_replayable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "run"
            result = runner.run(ROOT / "sources" / "ljcr-c1264-41.txt", output, 0.05, 7)
            self.assertEqual(result["candidate"]["blocks"], 40)
            receipt = auditor.audit(output / "result.json")
            self.assertEqual(receipt["metrics"], result["best_metrics"])


if __name__ == "__main__":
    unittest.main()

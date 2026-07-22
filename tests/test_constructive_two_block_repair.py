from __future__ import annotations

import importlib.util
import itertools
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


runner = load("run_constructive_two_block_repair", ROOT / "scripts" / "run_constructive_two_block_repair.py")
auditor = load("audit_constructive_repair_two", ROOT / "checkers" / "audit_constructive_repair.py")
SOURCE = ROOT / "artifacts" / "constructive" / "repair-seed126442-30s" / "best-candidate.txt"


class ConstructiveTwoBlockRepairTests(unittest.TestCase):
    def test_trade_preserves_point_degrees(self) -> None:
        selected = runner.read_candidate(SOURCE)
        _, point_counts, _ = runner.counts(selected)
        self.assertEqual(point_counts, [20] * 12)
        groups = runner.trade_groups()
        remove = next(pair for pair in itertools.combinations(sorted(selected), 2) if any(not set(add) & selected for add in groups.get(runner.signature(*pair), ())))
        add = next(add for add in groups[runner.signature(*remove)] if not set(add) & selected)
        updated = selected.difference(remove) | set(add)
        self.assertEqual(runner.counts(updated)[1], [20] * 12)

    def test_short_run_is_replayable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "run"
            result = runner.run(SOURCE, output, 0.05, 11)
            receipt = auditor.audit(output / "result.json")
            self.assertEqual(receipt["metrics"], result["best_metrics"])


if __name__ == "__main__":
    unittest.main()

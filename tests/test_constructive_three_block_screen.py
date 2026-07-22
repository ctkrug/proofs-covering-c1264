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


runner = load("three_block_runner", ROOT / "scripts" / "run_constructive_three_block_screen.py")
auditor = load("three_block_auditor", ROOT / "checkers" / "audit_three_block_screen.py")
SOURCE = ROOT / "artifacts" / "constructive" / "repair-seed126442-30s" / "best-candidate.txt"
CONTROL = ROOT / "sources" / "ljcr-c1264-41.txt"


class ConstructiveThreeBlockScreenTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.buckets = runner.pair_signature_buckets()

    def test_proposal_is_independent_of_two_block_neighborhood(self) -> None:
        import random

        selected = runner.read_candidate(SOURCE)
        quad_counts, point_counts, _ = runner.counts(selected)
        proposal = runner.propose(selected, quad_counts, self.buckets, random.Random(126460))
        self.assertIsNotNone(proposal)
        remove, add, target, _ = proposal
        self.assertEqual(runner.point_signature(remove), runner.point_signature(add))
        self.assertFalse(runner.decomposes_as_two_block(remove, add))
        self.assertEqual(quad_counts[target], 0)
        self.assertTrue(any(set(runner.QUADS[target]).issubset(runner.BLOCKS[index]) for index in add))
        updated = selected.difference(remove) | set(add)
        self.assertEqual(runner.counts(updated)[1], point_counts)

    def test_short_screen_replays_independently(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "screen"
            runner.run_screen(SOURCE, CONTROL, output, [11, 12], 60, 2.0)
            receipt = auditor.audit(output / "manifest.json")
            self.assertEqual(receipt["status"], "valid")
            self.assertEqual(receipt["seeds_audited"], 2)
            self.assertGreater(receipt["accepted_moves_replayed"], 0)


if __name__ == "__main__":
    unittest.main()

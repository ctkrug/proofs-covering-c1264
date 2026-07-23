from __future__ import annotations

import copy
import importlib.util
import json
import random
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "artifacts" / "constructive" / "repair-seed126442-30s" / "best-candidate.txt"


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


runner = load("slack_runner", ROOT / "scripts" / "run_constructive_slack_chain_discriminator.py")
checker = load("slack_checker", ROOT / "checkers" / "audit_slack_chain_discriminator.py")


class SlackChainTests(unittest.TestCase):
    def test_generated_chain_leaves_and_returns_to_exact_fibre(self) -> None:
        selected = runner.load_candidate(SOURCE)
        quad_counts, degrees, _ = runner.counts(selected)
        self.assertEqual(degrees, [20] * 12)
        proposal = None
        rng = random.Random(126480)
        for _ in range(100):
            proposal, _ = runner.propose_chain(selected, quad_counts, rng)
            if proposal is not None:
                break
        self.assertIsNotNone(proposal)
        assert proposal is not None
        endpoint = proposal["endpoint"]
        self.assertNotEqual(endpoint, selected)
        self.assertEqual(runner.counts(endpoint)[1], [20] * 12)
        self.assertEqual(len(set(proposal["remove"]) & set(proposal["add"])), 0)
        target = set(proposal["target_quad"])
        self.assertTrue(any(target.issubset(runner.BLOCKS[index]) for index in proposal["add"]))

    def test_short_trace_and_four_mutations(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "seed"
            result = runner.run_treatment_seed(SOURCE, output, 126480, 30, 3.0)
            events = [json.loads(raw) for raw in (output / "complete-chains.jsonl").read_text().splitlines()]
            self.assertTrue(events)
            selected = runner.load_candidate(SOURCE)
            checker.validate_chain_event(events[0], selected, 1, result["attempt_budget"])
            mutations = []
            first = copy.deepcopy(events[0])
            first["steps"][0]["add"] = next(index for index in selected if index != first["steps"][0]["remove"])
            mutations.append(first)
            second = copy.deepcopy(events[0])
            second["steps"][1]["source"] = second["cycle"][0]
            mutations.append(second)
            third = copy.deepcopy(events[0])
            third["steps"][3]["add"] = third["steps"][0]["add"]
            mutations.append(third)
            fourth = copy.deepcopy(events[0])
            fourth["steps"][2]["add"] = next(index for index in selected if index != fourth["steps"][2]["remove"])
            mutations.append(fourth)
            for mutation in mutations:
                with self.assertRaises(ValueError):
                    checker.validate_chain_event(mutation, selected, 1, result["attempt_budget"])


if __name__ == "__main__":
    unittest.main()

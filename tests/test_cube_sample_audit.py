from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


auditor = load("audit_cube_sample", ROOT / "checkers" / "audit_cube_sample.py")


class CubeSampleAuditTests(unittest.TestCase):
    def test_matches_rows_to_hash_bound_frontier(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            directory = Path(raw)
            frontier = directory / "frontier.json"
            frontier.write_text(json.dumps({
                "root_case": "test",
                "cubes": [
                    {"cube_id": 0, "literals": [-1, -2]},
                    {"cube_id": 1, "literals": [-1, 2]},
                ],
            }))
            results = directory / "results.jsonl"
            results.write_text(
                json.dumps({"cube_id": 0, "literals": [-1, -2], "elapsed_seconds": 1, "status": "UNKNOWN"}) + "\n" +
                json.dumps({"cube_id": 1, "literals": [-1, 2], "elapsed_seconds": 2, "status": "CLOSED_PROVISIONAL"}) + "\n"
            )
            value = auditor.audit(frontier, [results])
        self.assertEqual(value["status"], "valid")
        self.assertEqual(value["sampled_cubes"], 2)
        self.assertEqual(value["closed_provisional_fraction"], 0.5)

    def test_rejects_row_not_in_frontier(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            directory = Path(raw)
            frontier = directory / "frontier.json"
            frontier.write_text(json.dumps({"root_case": "test", "cubes": [{"cube_id": 0, "literals": [-1]}]}))
            results = directory / "results.jsonl"
            results.write_text(json.dumps({"cube_id": 0, "literals": [1], "elapsed_seconds": 1, "status": "UNKNOWN"}) + "\n")
            with self.assertRaisesRegex(ValueError, "does not match"):
                auditor.audit(frontier, [results])


if __name__ == "__main__":
    unittest.main()

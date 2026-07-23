#!/usr/bin/env python3
"""Regression tests for central-import ownership resolution."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "artifacts/classification/ordinary-c1153-v1/open-fifth-deficit-partition-v2/second-live-triple-gate-v1/shallow-weighted-scale-v1"
sys.path.insert(0, str(ROOT / "checkers"))

from import_ordinary_c1153_shallow_weighted_segment import resolve_owner  # noqa: E402


class CentralImportOwnershipTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.ledger = json.loads(
            (BASE / "hybrid-execution-v1/assignment-ledger.json").read_text()
        )

    def test_completed_before_split_segments_resolve_before_execution(self) -> None:
        self.assertEqual(
            resolve_owner(self.ledger, 0),
            {"branch": "main", "worker_id": "cloud"},
        )
        self.assertEqual(
            resolve_owner(self.ledger, 1),
            {"branch": "main", "worker_id": "cloud"},
        )
        self.assertEqual(
            resolve_owner(self.ledger, 2),
            {"branch": "main", "worker_id": "local-mac-benchmark"},
        )

    def test_frozen_worker_ranges_remain_unchanged(self) -> None:
        self.assertEqual(
            resolve_owner(self.ledger, 3),
            {"branch": "shallow-scale-cloud-003-030", "worker_id": "cloud-a"},
        )
        self.assertEqual(
            resolve_owner(self.ledger, 84),
            {"branch": "shallow-scale-local-058-084", "worker_id": "local-b"},
        )

    def test_unknown_segment_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "no frozen assignment owner"):
            resolve_owner(self.ledger, 85)


if __name__ == "__main__":
    unittest.main()

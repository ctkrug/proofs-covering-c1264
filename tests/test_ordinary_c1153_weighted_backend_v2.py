#!/usr/bin/env python3
"""Regression tests for the future-only weighted proposal backend v2."""

from __future__ import annotations

import gzip
import importlib.util
import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "artifacts/classification/ordinary-c1153-v1/open-fifth-deficit-partition-v2/second-live-triple-gate-v1"
REFERENCE = BASE / "shallow-weighted-scale-v1/segments/shallow-weighted-scale-002/outcomes.jsonl.gz"
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "checkers")]

from audit_ordinary_c1153_fourth_inventory import reconstruct_hierarchy  # noqa: E402
from ordinary_c1153_weighted_backend_v2 import (  # noqa: E402
    exact_check,
    install_exact_identity_cache,
    solve_highs,
)
from profile_ordinary_c1153_shallow_weighted_backend import domain_hashes  # noqa: E402
from run_ordinary_c1153_ilp_forced_gate import residual_domain  # noqa: E402
from run_ordinary_c1153_shallow_weighted_scale import (  # noqa: E402
    exact_certificate,
    open_jobs,
)


@unittest.skipUnless(importlib.util.find_spec("highspy"), "highspy proposal engine is not installed")
class WeightedBackendV2Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        references = [
            json.loads(line)
            for line in gzip.decompress(REFERENCE.read_bytes()).splitlines()
        ]
        cls.references = {row["case_id"]: row for row in references}
        cls.jobs = open_jobs()[4096:6144]
        cls.source_cases = {
            row["id"]: row for row in json.loads((BASE / "manifest.json").read_text())["target_cases"]
        }
        _, cls.parents, _, _ = reconstruct_hierarchy()
        install_exact_identity_cache()

    def test_quantile_sample_matches_domains_and_terminal_verdicts(self) -> None:
        for index in (0, 512, 1024, 1536, 2047):
            job = self.jobs[index]
            reference = self.references[job["case_id"]]
            case = self.source_cases[job["target_child_id"]]
            parent_id = Path(case["third_level_parent_cnf"]["path"]).parent.name
            domain = residual_domain(job, case, self.parents[parent_id])
            self.assertEqual(domain_hashes(domain), reference["domain"])
            status, duals, _ = solve_highs(
                [tuple(row) for row in domain["uncovered"]],
                domain["available"],
            )
            self.assertEqual(status, "Optimal")
            certificate = exact_certificate(
                duals, domain["available"], domain["remaining_slots"]
            )
            self.assertEqual(
                exact_check(domain, certificate),
                reference["certificate"] is not None,
            )

    def test_exact_checker_rejects_overloaded_block(self) -> None:
        domain = {
            "uncovered": [[1, 2, 3]],
            "available": [1],
            "remaining_slots": 0,
        }
        invalid = {
            "weights": [[1, 2, 3, 2]],
            "denominator": 1,
            "total_numerator": 2,
            "maximum_eligible_block_load": 2,
        }
        with self.assertRaises(ValueError):
            exact_check(domain, invalid)


if __name__ == "__main__":
    unittest.main()

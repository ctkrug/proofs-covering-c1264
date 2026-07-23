from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_sixth_hard_tail_partition_is_complete_and_disjoint() -> None:
    checker = load(
        "audit_sixth_hard_tail",
        ROOT / "checkers/audit_ordinary_c1153_sixth_hard_tail_discriminator.py",
    )
    report = checker.audit()
    assert report["status"] == "VALID"
    assert report["case_count"] == 82
    assert report["total_sixth_children"] == 11210
    assert report["duplicate_cases"] == 0
    assert report["omitted_timeout_cases"] == 0
    assert report["predecessor_cases_retained"] == 48
    assert report["new_timeout_cases_audited"] == 34
    assert report["predecessor_recipes_byte_equivalent"] is True
    assert report["changed_predecessor_recipes"] == []


def test_sixth_discriminator_results_reconstruct_and_replay() -> None:
    checker = load(
        "audit_sixth_results",
        ROOT / "checkers/audit_ordinary_c1153_sixth_discriminator_results.py",
    )
    report = checker.audit()
    assert report["status"] == "VALID"
    assert report["sample_count"] == 48
    assert report["independently_replayed_unsat"] == 34
    assert report["latter_verified_unsat"] == 24
    assert report["early_timeouts"] == 14
    assert report["latter_timeouts"] == 0
    assert report["hypothesis_supported"] is True

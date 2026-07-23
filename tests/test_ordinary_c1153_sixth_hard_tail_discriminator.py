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
    assert report["case_count"] > 0
    assert report["total_sixth_children"] >= report["case_count"]
    assert report["duplicate_cases"] == 0
    assert report["omitted_timeout_cases"] == 0

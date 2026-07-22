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


def test_fifth_split_is_complete_and_disjoint() -> None:
    checker = load("audit_fifth", ROOT / "checkers/audit_ordinary_c1153_fifth_split.py")
    report = checker.audit()
    assert report["status"] == "VALID"
    assert report["parent_count"] == 384
    assert report["total_branches"] == 43319


def test_fourth_ledger_arithmetic_is_exact() -> None:
    import json

    report = json.loads((ROOT / "artifacts/classification/ordinary-c1153-v1/hard-tail-fourth-split/fourth-level-ledger-audit.json").read_text())
    assert report["status"] == "VALID"
    assert report["suffix_expected"] == report["suffix_actual"] == 386
    assert report["duplicate_measured_cases"] == 0
    assert report["omitted_selected_suffix_cases"] == 0
    assert report["counts"] == {
        "universe": 790,
        "replay_verified_unsat": 406,
        "fixed_cap_timeout": 32,
        "never_measured": 352,
        "open": 384,
    }

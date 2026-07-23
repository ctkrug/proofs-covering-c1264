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


def test_suffix_scale_selection_and_segment_zero_receipt() -> None:
    import json

    base = ROOT / "artifacts/classification/ordinary-c1153-v1/hard-tail-fifth-split"
    selection = json.loads((base / "suffix-scale-independent-audit.json").read_text())
    assert selection["status"] == "VALID"
    assert selection["suffix_universe"] == 32645
    assert selection["excluded_measured"] == 48
    assert selection["pending_unique"] == 32597
    assert selection["duplicate_cases"] == selection["omitted_pending_cases"] == 0

    segment = json.loads((base / "segments/segment-0000/independent-audit.json").read_text())
    assert segment["status"] == "VALID"
    assert segment["selected"] == segment["completed"] == 256
    assert segment["counts"] == {
        "FIXED_CAP_TIMEOUT": 0,
        "INDEPENDENT_SAMPLE_UNSAT_REPLAYED": 32,
        "RUNNER_UNSAT_REPLAYED": 256,
        "SAT_VALIDATED": 0,
    }
    assert segment["replay_success_rate"] == 1.0
    assert segment["complete_fourth_parents_closed"] == 0
    assert segment["remaining_route_branches"] == 32341
    assert segment["continuation_gate_passed"] is True


def test_streaming_exact_cnf_is_byte_identical() -> None:
    import hashlib
    import json
    import tempfile

    runner = load("fifth_suffix_runner", ROOT / "scripts/run_ordinary_c1153_fifth_suffix_segment.py")
    base = ROOT / "artifacts/classification/ordinary-c1153-v1/hard-tail-fifth-split"
    fifth = json.loads((base / "manifest.json").read_text())
    parent_by_id = {row["id"]: row for row in fifth["parents"]}
    result_path = next((base / "segments/segment-0000").glob("*/result.json"))
    result = json.loads(result_path.read_text())
    parent = parent_by_id[result["fourth_parent_id"]]
    units = parent["inherited_fourth_units"] + runner.fifth_units(parent, result["fifth_index"])
    with tempfile.TemporaryDirectory() as temporary:
        target = Path(temporary) / "exact.cnf"
        runner.write_exact_cnf(ROOT / parent["third_level_parent_cnf"]["path"], units, target)
        digest = hashlib.sha256(target.read_bytes()).hexdigest()
    assert digest == result["exact_cnf_sha256"]


def test_suffix_ledgers_are_explicit_and_arithmetically_sound() -> None:
    import json

    ledger = json.loads((ROOT / "artifacts/classification/ordinary-c1153-v1/hard-tail-fifth-split/suffix-scale-ledger.json").read_text())
    assert ledger["totals"] == {
        "certified_independent_replay": 346,
        "completed": 2816,
        "compressed_proof_bytes": 318154011,
        "fixed_cap_timeout": 6,
        "provisional_solver_unsat": 2810,
        "sat": 0,
        "selected": 2816,
    }
    assert ledger["remaining_unmeasured_scale_jobs"] == 29781
    assert ledger["totals"]["provisional_solver_unsat"] + ledger["totals"]["fixed_cap_timeout"] == ledger["totals"]["completed"]
    assert ledger["totals"]["certified_independent_replay"] <= ledger["totals"]["provisional_solver_unsat"]
    assert ledger["complete_fourth_parents_closed"] == 0

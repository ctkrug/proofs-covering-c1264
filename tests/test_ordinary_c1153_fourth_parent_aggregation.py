from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "artifacts/classification/ordinary-c1153-v1/fourth-parent-aggregation-v2"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_independent_aggregation_receipt() -> None:
    summary_path = BASE / "summary.json"
    audit_path = BASE / "independent-audit.json"
    summary = json.loads(summary_path.read_text())
    audit = json.loads(audit_path.read_text())
    assert audit["status"] == "VALID"
    assert audit["summary_sha256"] == sha(summary_path)
    assert summary["counts"] == audit["counts"] == {
        "fifth_children_total": 43_319,
        "fourth_parents_closed": 216,
        "fourth_parents_open": 168,
        "fourth_parents_total": 384,
        "remaining_open_children": 2_232,
        "replay_certified_unsat_children": 32_611,
        "semantic_contradiction_children": 8_476,
    }
    assert len(audit["newly_closed_fourth_parent_ids"]) == 216
    assert len(audit["remaining_fourth_parent_ids"]) == 168


def test_every_closed_parent_has_only_explicit_terminals() -> None:
    summary = json.loads((BASE / "summary.json").read_text())
    checked = 0
    for row in summary["parents"]:
        receipt_path = ROOT / row["receipt"]["path"]
        assert sha(receipt_path) == row["receipt"]["sha256"]
        receipt = json.loads(receipt_path.read_text())
        if row["parent_status"] != "CLOSED_BY_EXHAUSTIVE_CHILD_AGGREGATION":
            continue
        checked += 1
        assert receipt["remaining_children"] == 0
        assert receipt["terminal_children"] == receipt["child_count"]
        assert all(child["terminal"] for child in receipt["children"])
        assert all(
            child["terminal_status"]
            in {
                "REPLAY_CERTIFIED_UNSAT",
                "AUDITED_SEMANTIC_COVERAGE_CONTRADICTION",
            }
            for child in receipt["children"]
        )
    assert checked == 216


def test_semantic_contradictions_are_not_labeled_solver_unsat() -> None:
    summary = json.loads((BASE / "summary.json").read_text())
    semantic = 0
    for row in summary["parents"]:
        receipt = json.loads((ROOT / row["receipt"]["path"]).read_text())
        for child in receipt["children"]:
            if child["terminal_status"] != "AUDITED_SEMANTIC_COVERAGE_CONTRADICTION":
                continue
            semantic += 1
            assert child["certification_kind"] == "EMPTY_RESIDUAL_COVERAGE_CLAUSE"
            assert "proof_sha256" not in child
            assert child["semantic_receipt"]["semantic_status"] == (
                "EMPTY_RESIDUAL_COVERAGE_CLAUSE_NOT_YET_SOLVER_CERTIFIED"
            )
    assert semantic == 8_476

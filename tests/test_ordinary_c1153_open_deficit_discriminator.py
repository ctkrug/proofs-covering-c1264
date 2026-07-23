from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "artifacts/classification/ordinary-c1153-v1/open-fifth-deficit-partition-v2"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_frozen_sample_is_exactly_balanced_and_audited() -> None:
    protocol = json.loads((BASE / "discriminator-v2/protocol.json").read_text())
    summary = json.loads((BASE / "discriminator-v2/summary.json").read_text())
    audit = json.loads((BASE / "discriminator-v2/independent-audit.json").read_text())
    parents = {
        row["fifth_case_id"]: row
        for row in protocol["sample"]
        if row["deficit_position"] == "first_deficit_orbit"
    }
    assert protocol["sample_size"] == len(protocol["sample"]) == 48
    assert len(parents) == 24
    assert Counter(row["top_parent"] for row in parents.values()) == {
        "intersection-3": 12,
        "intersection-4": 12,
    }
    assert Counter(row["open_status"] for row in parents.values()) == {
        "FIXED_CAP_TIMEOUT": 12,
        "NEVER_MEASURED": 12,
    }
    assert Counter(row["first_eligible_rank_band"] for row in parents.values()) == {
        "rank_zero": 12,
        "rank_one": 4,
        "later_rank": 8,
    }
    assert Counter(row["stabilizer_tier"] for row in parents.values()) == {
        "low": 8,
        "mid": 8,
        "high": 8,
    }
    assert Counter(row["branch_count_quantile"] for row in parents.values()) == {
        "q1": 6,
        "q2": 6,
        "q3": 6,
        "q4": 6,
    }
    assert audit["status"] == "VALID"
    assert audit["protocol_sha256"] == sha(BASE / "discriminator-v2/protocol.json")
    assert audit["summary_sha256"] == sha(BASE / "discriminator-v2/summary.json")
    assert audit["counts"] == summary["counts"] == {
        "FIXED_CAP_TIMEOUT": 38,
        "UNSAT_VERIFIED_BY_RUNNER": 10,
    }
    assert audit["independently_replayed_unsat"] == 10
    assert audit["remaining_nonempty_children"] == 19640
    assert audit["complete_fifth_parent_count"] == 0


def test_zero_child_semantic_ledger_is_separate_and_verified() -> None:
    ledger = json.loads((BASE / "semantic-contradiction-ledger.json").read_text())
    audit = json.loads(
        (BASE / "semantic-contradiction-independent-audit.json").read_text()
    )
    assert ledger["status"] == "BUILT_PENDING_INDEPENDENT_VERIFIER"
    assert audit["status"] == "VALID"
    assert audit["ledger_sha256"] == sha(BASE / "semantic-contradiction-ledger.json")
    assert audit["verified_entries"] == ledger["entry_count"] == 8476
    assert audit["semantic_status_counts"] == {
        "EMPTY_RESIDUAL_COVERAGE_CLAUSE_VERIFIER_CHECKED": 8476
    }
    assert "not a DRAT" in audit["claim_limit"]

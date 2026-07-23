#!/usr/bin/env python3
"""Independently audit the disjoint hybrid shallow-scale assignment."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "artifacts/classification/ordinary-c1153-v1/open-fifth-deficit-partition-v2/second-live-triple-gate-v1/shallow-weighted-scale-v1"
LEDGER = BASE / "hybrid-execution-v1/assignment-ledger.json"
MANIFEST = BASE / "manifest.json"
RUNNER = ROOT / "scripts/run_ordinary_c1153_shallow_weighted_scale.py"
CHECKER = ROOT / "checkers/audit_ordinary_c1153_shallow_weighted_scale.py"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    ledger = json.loads(LEDGER.read_text())
    manifest = json.loads(MANIFEST.read_text())
    if ledger["status"] != "FROZEN":
        raise ValueError("assignment ledger is not frozen")
    if ledger["manifest_sha256"] != sha(MANIFEST):
        raise ValueError("manifest binding mismatch")
    if ledger["generator_sha256"] != sha(RUNNER):
        raise ValueError("generator binding mismatch")
    if ledger["checker_sha256"] != sha(CHECKER):
        raise ValueError("checker binding mismatch")
    if manifest["segment_count"] != 85:
        raise ValueError("frozen manifest does not contain exactly 85 segments")

    ownership: dict[int, str] = {}
    for completed in ledger["completed_before_split"]:
        for number in completed["segments"]:
            if number in ownership:
                raise ValueError(f"duplicate completed segment {number}")
            ownership[number] = completed["host"]
    for assignment in ledger["assignments"]:
        expected_count = assignment["last_segment"] - assignment["first_segment"] + 1
        if assignment["segment_count"] != expected_count:
            raise ValueError(f"{assignment['worker_id']}: range/count mismatch")
        for number in range(assignment["first_segment"], assignment["last_segment"] + 1):
            if number in ownership:
                raise ValueError(f"duplicate assigned segment {number}")
            ownership[number] = assignment["worker_id"]

    expected = set(range(85))
    actual = set(ownership)
    if actual != expected:
        raise ValueError(
            f"assignment coverage mismatch: missing={sorted(expected - actual)}, "
            f"extra={sorted(actual - expected)}"
        )
    if ledger["unassigned_segment_ids"] or ledger["duplicate_segment_ids"]:
        raise ValueError("ledger declares unassigned or duplicate segments")

    report = {
        "schema_version": 1,
        "status": "VALID",
        "assignment_ledger_sha256": sha(LEDGER),
        "manifest_sha256": sha(MANIFEST),
        "segment_count": len(actual),
        "completed_before_split": 3,
        "newly_assigned": 82,
        "worker_ranges": {
            row["worker_id"]: [row["first_segment"], row["last_segment"]]
            for row in ledger["assignments"]
        },
        "missing_segment_ids": [],
        "duplicate_segment_ids": [],
        "claim_limit": "This audit proves execution ownership and coverage only; it does not certify formulas or ancestors.",
    }
    output = LEDGER.parent / "assignment-independent-audit.json"
    raw = (json.dumps(report, sort_keys=True, separators=(",", ":")) + "\n").encode()
    if output.exists() and output.read_bytes() != raw:
        raise ValueError("refusing to replace incompatible assignment audit")
    output.write_bytes(raw)
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

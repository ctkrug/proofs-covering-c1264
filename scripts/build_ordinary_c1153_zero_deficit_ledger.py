#!/usr/bin/env python3
"""Build a compact ledger for exact zero-child semantic contradictions."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "artifacts/classification/ordinary-c1153-v1/open-fifth-deficit-partition-v2"
MANIFEST = BASE / "manifest.json"
AUDIT = BASE / "independent-audit.json"
OUTPUT = BASE / "semantic-contradiction-ledger.json"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def object_sha(value: object) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()


def build() -> dict[str, object]:
    manifest, audit = json.loads(MANIFEST.read_text()), json.loads(AUDIT.read_text())
    if audit["status"] != "VALID" or audit["manifest_sha256"] != sha(MANIFEST):
        raise ValueError("partition audit gate failed")
    entries = []
    reason_counts: Counter[str] = Counter()
    for case in manifest["cases"]:
        if case["branch_count"] != 0:
            continue
        receipt = case["semantic_contradiction_receipt"]
        if receipt is None:
            raise ValueError(f"{case['id']}: zero child lacks receipt")
        for coverer in receipt["forbidden_coverers"]:
            reason_counts.update(coverer["reasons"])
        entries.append(
            {
                "fifth_case_id": case["id"],
                "open_status": case["open_status"],
                "top_parent": case["top_parent"],
                "third_level_parent_cnf_sha256": case["third_level_parent_cnf"]["sha256"],
                "inherited_unit_sha256": case["inherited_unit_sha256"],
                "selected_triple": receipt["selected_triple"],
                "coverage_clause_sha256": receipt["coverage_clause_sha256"],
                "receipt_sha256": object_sha(receipt),
                "semantic_status": "EMPTY_RESIDUAL_COVERAGE_CLAUSE_VERIFIER_PENDING",
            }
        )
    if len(entries) != manifest["zero_child_cases"] != 0:
        raise ValueError("zero-child ledger count mismatch")
    ledger = {
        "schema_version": 1,
        "status": "BUILT_PENDING_INDEPENDENT_VERIFIER",
        "partition_manifest": {
            "path": str(MANIFEST.relative_to(ROOT)),
            "sha256": sha(MANIFEST),
        },
        "partition_audit": {
            "path": str(AUDIT.relative_to(ROOT)),
            "sha256": sha(AUDIT),
        },
        "entry_count": len(entries),
        "entry_ids_sha256": hashlib.sha256(
            ("\n".join(entry["fifth_case_id"] for entry in entries) + "\n").encode()
        ).hexdigest(),
        "forbidden_reason_occurrences": dict(reason_counts),
        "entries": entries,
        "claim_limit": (
            "These are exact finite coverage-clause contradictions, not solver-UNSAT "
            "statuses or DRAT certificates. They may be called verifier-checked only "
            "after the separate semantic-ledger audit passes."
        ),
    }
    OUTPUT.write_text(json.dumps(ledger, sort_keys=True, separators=(",", ":")) + "\n")
    return ledger


if __name__ == "__main__":
    report = build()
    print(
        json.dumps(
            {
                "status": report["status"],
                "entry_count": report["entry_count"],
                "forbidden_reason_occurrences": report["forbidden_reason_occurrences"],
            },
            indent=2,
            sort_keys=True,
        )
    )

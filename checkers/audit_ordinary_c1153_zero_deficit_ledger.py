#!/usr/bin/env python3
"""Independently verify the zero-child semantic contradiction ledger."""

from __future__ import annotations

import hashlib
import itertools
import json
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "artifacts/classification/ordinary-c1153-v1/open-fifth-deficit-partition-v2"
MANIFEST = BASE / "manifest.json"
LEDGER = BASE / "semantic-contradiction-ledger.json"
OUTPUT = BASE / "semantic-contradiction-independent-audit.json"
BLOCKS = tuple(itertools.combinations(range(1, 12), 5))


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def object_sha(value: object) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()


def clause_sha(values: list[int]) -> str:
    payload = " ".join(map(str, values)) + (" " if values else "") + "0\n"
    return hashlib.sha256(payload.encode()).hexdigest()


def parent_negative_units(path: Path) -> set[int]:
    result: set[int] = set()
    with path.open() as source:
        for line in source:
            if not line or line[0] in "cp%0":
                continue
            words = line.split()
            if len(words) == 2 and words[1] == "0":
                value = int(words[0])
                if -len(BLOCKS) <= value < 0:
                    result.add(-value)
    return result


def audit() -> dict[str, object]:
    manifest, ledger = json.loads(MANIFEST.read_text()), json.loads(LEDGER.read_text())
    if ledger["partition_manifest"]["sha256"] != sha(MANIFEST):
        raise ValueError("ledger/partition binding mismatch")
    cases = {case["id"]: case for case in manifest["cases"]}
    entries = {entry["fifth_case_id"]: entry for entry in ledger["entries"]}
    expected_ids = {case["id"] for case in manifest["cases"] if case["branch_count"] == 0}
    if len(entries) != len(ledger["entries"]) or set(entries) != expected_ids:
        raise ValueError("zero-child membership mismatch")
    positions = {block: index for index, block in enumerate(BLOCKS, 1)}
    cache: dict[str, set[int]] = {}
    status_counts: Counter[str] = Counter()
    open_counts: Counter[str] = Counter()
    reason_counts: Counter[str] = Counter()
    for case_id in sorted(expected_ids):
        case, entry = cases[case_id], entries[case_id]
        receipt = case["semantic_contradiction_receipt"]
        parent_path = ROOT / case["third_level_parent_cnf"]["path"]
        parent_key = str(parent_path)
        if parent_key not in cache:
            if sha(parent_path) != case["third_level_parent_cnf"]["sha256"]:
                raise ValueError(f"{case_id}: parent hash mismatch")
            cache[parent_key] = parent_negative_units(parent_path)
        parent_negative = cache[parent_key]
        inherited_negative = {-value for value in case["inherited_units"] if value < 0}
        absent = parent_negative | inherited_negative
        triple = tuple(receipt["selected_triple"])
        coverers = sorted(
            positions[tuple(sorted((*triple, *pair)))]
            for pair in itertools.combinations(
                sorted(set(range(1, 12)) - set(triple)), 2
            )
        )
        forbidden = []
        for value in coverers:
            reasons = []
            if value in parent_negative:
                reasons.append("PARENT_CNF_NEGATIVE_UNIT")
            if value in inherited_negative:
                reasons.append("INHERITED_NEGATIVE_UNIT")
            if not reasons:
                raise ValueError(f"{case_id}: coverer remains eligible")
            forbidden.append({"variable": value, "reasons": reasons})
            reason_counts.update(reasons)
        if (
            receipt["coverage_clause_variables"] != coverers
            or receipt["coverage_clause_sha256"] != clause_sha(coverers)
            or receipt["forbidden_coverers"] != forbidden
            or receipt["residual_eligible_variables"] != []
            or receipt["empty_residual_clause_sha256"] != clause_sha([])
            or any(value not in absent for value in coverers)
        ):
            raise ValueError(f"{case_id}: semantic receipt mismatch")
        expected_entry = {
            "fifth_case_id": case_id,
            "open_status": case["open_status"],
            "top_parent": case["top_parent"],
            "third_level_parent_cnf_sha256": case["third_level_parent_cnf"]["sha256"],
            "inherited_unit_sha256": case["inherited_unit_sha256"],
            "selected_triple": list(triple),
            "coverage_clause_sha256": clause_sha(coverers),
            "receipt_sha256": object_sha(receipt),
            "semantic_status": "EMPTY_RESIDUAL_COVERAGE_CLAUSE_VERIFIER_PENDING",
        }
        if entry != expected_entry:
            raise ValueError(f"{case_id}: ledger entry mismatch")
        status_counts["EMPTY_RESIDUAL_COVERAGE_CLAUSE_VERIFIER_CHECKED"] += 1
        open_counts[case["open_status"]] += 1
    if reason_counts != Counter(ledger["forbidden_reason_occurrences"]):
        raise ValueError("forbidden-reason aggregate mismatch")
    return {
        "schema_version": 1,
        "status": "VALID",
        "ledger_sha256": sha(LEDGER),
        "partition_manifest_sha256": sha(MANIFEST),
        "verified_entries": len(entries),
        "semantic_status_counts": dict(status_counts),
        "source_open_status_counts": dict(open_counts),
        "forbidden_reason_occurrences": dict(reason_counts),
        "claim_limit": (
            "All listed fifth cases have a directly verified empty residual triple-coverage "
            "clause. This is a semantic finite contradiction ledger, not a DRAT replay ledger "
            "or a solver-UNSAT count."
        ),
    }


if __name__ == "__main__":
    report = audit()
    OUTPUT.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, indent=2, sort_keys=True))

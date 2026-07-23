#!/usr/bin/env python3
"""Independently audit the backend-v2 activation receipt."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "artifacts/classification/ordinary-c1153-v1/open-fifth-deficit-partition-v2/second-live-triple-gate-v1/shallow-weighted-scale-v1"
OUT = BASE / "backend-upgrade-v1"
RECEIPT = OUT / "receipt.json"
AUDIT = OUT / "independent-audit.json"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check_ref(value: dict[str, str]) -> Path:
    path = ROOT / value["path"]
    if not path.is_file() or sha(path) != value["sha256"]:
        raise ValueError(f"bad backend-upgrade binding: {value}")
    return path


def write(value: object) -> None:
    raw = (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()
    if AUDIT.exists():
        if AUDIT.read_bytes() != raw:
            raise ValueError("refusing incompatible backend-upgrade audit")
        return
    temporary = AUDIT.with_suffix(".tmp")
    temporary.write_bytes(raw)
    os.replace(temporary, AUDIT)


def main() -> None:
    receipt = json.loads(RECEIPT.read_text())
    manifest = json.loads(check_ref(receipt["frozen_shallow_scale_manifest"]).read_text())
    check_ref(receipt["v2_generator"])
    check_ref(receipt["v2_backend"])
    checker = check_ref(receipt["unchanged_independent_segment_checker"])
    evidence = receipt["benchmark_evidence"]
    reference = check_ref(evidence["input_reference_archive"])
    summary = json.loads(check_ref(evidence["benchmark_summary"]).read_text())
    benchmark_audit = json.loads(
        check_ref(evidence["independent_equivalence_audit"]).read_text()
    )
    if manifest["status"] != "FROZEN" or manifest["open_formula_count"] != 173832:
        raise ValueError("frozen shallow-scale domain changed")
    if summary["input"]["reference_archive_sha256"] != sha(reference):
        raise ValueError("benchmark input archive mismatch")
    if (
        benchmark_audit["status"] != "VALID"
        or benchmark_audit["formula_membership_and_order_agreement"] != 2048
        or benchmark_audit["independently_reconstructed_domain_agreement"] != 2048
        or benchmark_audit["terminal_nonterminal_verdict_agreement"] != 2048
        or benchmark_audit["independently_checked_exact_certificates"] != 2043
        or benchmark_audit["open_reference_gaps"] != 5
    ):
        raise ValueError("benchmark equivalence evidence is incomplete")
    if checker.name != "audit_ordinary_c1153_shallow_weighted_scale.py":
        raise ValueError("activation does not bind the unchanged campaign checker")
    rule = receipt["heterogeneous_generator_rule"]
    for phrase in (
        "exact source CNF",
        "residual-domain hashes",
        "exact and unique",
        "independent block-by-block checker",
        "never",
    ):
        if phrase not in rule:
            raise ValueError(f"heterogeneous-generator rule omits {phrase}")
    report = {
        "schema_version": 1,
        "status": "VALID",
        "receipt_sha256": sha(RECEIPT),
        "frozen_manifest_sha256": receipt["frozen_shallow_scale_manifest"]["sha256"],
        "v2_generator_sha256": receipt["v2_generator"]["sha256"],
        "v2_backend_sha256": receipt["v2_backend"]["sha256"],
        "unchanged_checker_sha256": receipt[
            "unchanged_independent_segment_checker"
        ]["sha256"],
        "benchmark_formula_coverage": 2048,
        "benchmark_domain_hash_agreement": 2048,
        "benchmark_terminal_verdict_agreement": 2048,
        "benchmark_certificates_independently_accepted": 2043,
        "benchmark_open_gaps": 5,
        "heterogeneous_generator_rule_checked": True,
        "past_artifact_effect": "NONE",
        "mathematical_ledger_effect": "NONE",
    }
    write(report)
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

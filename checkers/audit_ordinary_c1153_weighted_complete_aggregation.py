#!/usr/bin/env python3
"""Independently audit the exhaustive 4,402-cube aggregation receipts."""

from __future__ import annotations

import hashlib
import json
import os
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GATE = ROOT / "artifacts/classification/ordinary-c1153-v1/open-fifth-deficit-partition-v2/second-live-triple-gate-v1/multi-deficit-propagation-gate-v1"
STRUCTURAL = GATE / "manifest.json"
OUT = GATE / "weighted-complete-aggregation-v1"
SUMMARY = OUT / "summary.json"
AUDIT = OUT / "independent-audit.json"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_sha(value: object) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()


def case_id(formula_id: str, path: list[int]) -> str:
    return f"{formula_id}-cube-{path[0]:03d}-{path[1]:03d}"


def write_json(path: Path, value: object) -> None:
    raw = (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()
    if path.exists():
        if path.read_bytes() != raw:
            raise ValueError(f"refusing to replace incompatible audit: {path}")
        return
    temporary = path.with_suffix(".tmp")
    temporary.write_bytes(raw)
    os.replace(temporary, path)


def check_ref(ref: dict[str, object]) -> Path:
    path = ROOT / str(ref["path"])
    if not path.is_file() or sha(path) != ref["sha256"]:
        raise ValueError(f"bad bound artifact: {ref}")
    return path


def main() -> None:
    structural = json.loads(STRUCTURAL.read_text())
    summary = json.loads(SUMMARY.read_text())
    check_ref(summary["bindings"]["structural_manifest"])
    check_ref(summary["bindings"]["scale_manifest"])

    expected_by_formula: dict[str, set[str]] = {}
    for formula in structural["formulas"]:
        ids = {
            case_id(formula["leaf_id"], terminal["path"])
            for terminal in formula["terminal_partition"]
            if terminal["kind"] == "frontier"
        }
        if len(ids) != formula["frontier_count"]:
            raise ValueError(f"{formula['leaf_id']}: structural frontier mismatch")
        expected_by_formula[formula["leaf_id"]] = ids

    seen: set[str] = set()
    source_counts: Counter[str] = Counter()
    for row in summary["formulas"]:
        receipt_path = check_ref(row["receipt"])
        receipt = json.loads(receipt_path.read_text())
        formula_id = row["formula_id"]
        if receipt["formula_id"] != formula_id or receipt["formula_status"] != "CLOSED_BY_EXHAUSTIVE_WEIGHTED_CHILD_AGGREGATION":
            raise ValueError(f"{formula_id}: invalid formula receipt")
        child_ids = {child["case_id"] for child in receipt["children"]}
        if len(child_ids) != len(receipt["children"]) or child_ids != expected_by_formula[formula_id]:
            raise ValueError(f"{formula_id}: child partition is not exact")
        for child in receipt["children"]:
            cid = child["case_id"]
            if cid in seen:
                raise ValueError(f"duplicate child across formulas: {cid}")
            seen.add(cid)
            if child["terminal_status"] != "AUDITED_WEIGHTED_ARITHMETIC_CONTRADICTION":
                raise ValueError(f"{cid}: nonterminal child")
            check_ref(child["certificate"])
            audit_path = check_ref(child["independent_audit"])
            source_audit = json.loads(audit_path.read_text())
            if source_audit["status"] != "VALID":
                raise ValueError(f"{cid}: source audit is not valid")
            if "compact_receipt" in child:
                compact_path = check_ref(child["compact_receipt"])
                compact = json.loads(compact_path.read_text())
                if compact["case_id"] != cid:
                    raise ValueError(f"{cid}: compact receipt membership mismatch")
            else:
                result_path = check_ref(child["source_result"])
                result = json.loads(result_path.read_text())
                if result["case_id"] != cid:
                    raise ValueError(f"{cid}: pilot result membership mismatch")
            source_counts[child["source_kind"]] += 1

    expected_all = set().union(*expected_by_formula.values())
    if len(expected_all) != 4402 or seen != expected_all:
        raise ValueError("global child coverage is not exactly 4,402")
    if summary["case_ids_sha256"] != canonical_sha(sorted(seen)):
        raise ValueError("global child identity hash mismatch")
    if summary["formula_count"] != 12 or summary["formulas_closed"] != 12:
        raise ValueError("formula aggregation count mismatch")
    if summary["source_kind_counts"] != dict(sorted(source_counts.items())):
        raise ValueError("source-kind aggregation mismatch")
    if any(summary["ancestor_effect"][key] for key in (
        "target_children_closed",
        "fifth_leaves_closed",
        "fourth_parents_closed",
        "ordinary_classification_closed",
        "global_extension_ledger_change",
    )):
        raise ValueError("unsupported ancestor effect asserted")

    audit = {
        "schema_version": 1,
        "status": "VALID",
        "summary_sha256": sha(SUMMARY),
        "structural_manifest_sha256": sha(STRUCTURAL),
        "exact_frontier_membership": 4402,
        "duplicate_or_missing_children": 0,
        "bound_terminal_children": len(seen),
        "formulas_independently_aggregated_closed": 12,
        "source_kind_counts": dict(sorted(source_counts.items())),
        "ancestor_effect": summary["ancestor_effect"],
        "claim_limit": "The 12 selected second-live formulas close. Their target children and all higher ancestors remain open absent a separate complete aggregation.",
    }
    write_json(AUDIT, audit)
    print(json.dumps(audit, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

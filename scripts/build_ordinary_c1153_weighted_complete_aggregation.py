#!/usr/bin/env python3
"""Build child-by-child receipts for the complete 4,402-cube partition."""

from __future__ import annotations

import hashlib
import json
import os
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GATE = ROOT / "artifacts/classification/ordinary-c1153-v1/open-fifth-deficit-partition-v2/second-live-triple-gate-v1/multi-deficit-propagation-gate-v1"
STRUCTURAL = GATE / "manifest.json"
ILP = GATE / "ilp-forced-gate-v1"
WEIGHTED = GATE / "weighted-generalization-gate-v1"
COMPACT = WEIGHTED / "compact-package-v1"
SCALE = COMPACT / "scale-manifest.json"
OUT = GATE / "weighted-complete-aggregation-v1"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_sha(value: object) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()


def relative(path: Path) -> str:
    return str(path.relative_to(ROOT))


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()
    if path.exists():
        if path.read_bytes() != raw:
            raise ValueError(f"refusing to replace incompatible aggregation artifact: {path}")
        return
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(raw)
    os.replace(temporary, path)


def case_id(formula_id: str, path: list[int]) -> str:
    return f"{formula_id}-cube-{path[0]:03d}-{path[1]:03d}"


def source_ref(path: Path) -> dict[str, object]:
    return {"path": relative(path), "sha256": sha(path)}


def load_terminal_sources() -> dict[str, dict[str, object]]:
    terminals: dict[str, dict[str, object]] = {}

    ilp_protocol_path = ILP / "protocol.json"
    ilp_summary_path = ILP / "summary.json"
    ilp_audit_path = ILP / "independent-audit.json"
    ilp_protocol = json.loads(ilp_protocol_path.read_text())
    ilp_summary = json.loads(ilp_summary_path.read_text())
    ilp_audit = json.loads(ilp_audit_path.read_text())
    if ilp_audit["status"] != "VALID" or ilp_audit["case_count"] != 6:
        raise ValueError("six-case weighted pilot audit is not valid")
    if ilp_audit["protocol_sha256"] != sha(ilp_protocol_path) or ilp_audit["summary_sha256"] != sha(ilp_summary_path):
        raise ValueError("six-case weighted pilot audit binding failed")
    outcomes = {row["case_id"]: row for row in ilp_summary["outcomes"]}
    for row in ilp_protocol["cases"]:
        cid = row["case_id"]
        result_path = ILP / "results" / cid / "result.json"
        result = json.loads(result_path.read_text())
        if result != outcomes[cid]:
            raise ValueError(f"{cid}: pilot result/summary mismatch")
        cert = result["base_weighted_certificate"]
        cert_path = ROOT / cert["path"]
        if sha(cert_path) != cert["sha256"]:
            raise ValueError(f"{cid}: pilot certificate hash mismatch")
        terminals[cid] = {
            "terminal_status": "AUDITED_WEIGHTED_ARITHMETIC_CONTRADICTION",
            "source_kind": "SIX_CASE_PILOT",
            "source_result": source_ref(result_path),
            "certificate": source_ref(cert_path),
            "independent_audit": source_ref(ilp_audit_path),
        }

    compact_audit_path = COMPACT / "independent-audit.json"
    compact_audit = json.loads(compact_audit_path.read_text())
    weighted_protocol = json.loads((WEIGHTED / "protocol.json").read_text())
    if compact_audit["status"] != "VALID" or compact_audit["case_count"] != 96:
        raise ValueError("96-case compact audit is not valid")
    for row in weighted_protocol["cases"]:
        cid = row["case_id"]
        receipt_path = COMPACT / "receipts" / f"{cid}.json"
        receipt = json.loads(receipt_path.read_text())
        cert_path = ROOT / receipt["compact_certificate_path"]
        if receipt["checker_status"] != "VALID" or sha(cert_path) != receipt["compact_certificate_sha256"]:
            raise ValueError(f"{cid}: invalid compact weighted receipt")
        if cid in terminals:
            raise ValueError(f"duplicate pilot/generalization case: {cid}")
        terminals[cid] = {
            "terminal_status": "AUDITED_WEIGHTED_ARITHMETIC_CONTRADICTION",
            "source_kind": "NINETY_SIX_CASE_GENERALIZATION",
            "compact_receipt": source_ref(receipt_path),
            "certificate": source_ref(cert_path),
            "independent_audit": source_ref(compact_audit_path),
        }

    scale = json.loads(SCALE.read_text())
    for segment in scale["segments"]:
        sid = segment["segment_id"]
        segment_dir = COMPACT / "scale-segments" / sid
        audit_path = segment_dir / "independent-audit.json"
        audit = json.loads(audit_path.read_text())
        if audit["status"] != "VALID" or audit["selected"] != segment["case_count"]:
            raise ValueError(f"{sid}: invalid or incomplete independent audit")
        if audit["independently_checked_weighted_obstructions"] != segment["case_count"]:
            raise ValueError(f"{sid}: certificate count mismatch")
        for index, row in enumerate(segment["cases"]):
            cid = row["case_id"]
            receipt_candidates = [
                segment_dir / "receipts" / f"{index:03d}.json",
                segment_dir / "receipts" / f"{cid}.json",
            ]
            receipt_path = next((path for path in receipt_candidates if path.exists()), None)
            if receipt_path is None:
                raise ValueError(f"{cid}: missing scale receipt")
            receipt = json.loads(receipt_path.read_text())
            if receipt["case_id"] != cid:
                raise ValueError(f"{cid}: scale receipt membership mismatch")
            cert_ref = receipt.get("certificate")
            if cert_ref is None:
                cert_path = ROOT / receipt["compact_certificate_path"]
                cert_hash = receipt["compact_certificate_sha256"]
            else:
                cert_path = ROOT / cert_ref["path"]
                cert_hash = cert_ref["sha256"]
            if sha(cert_path) != cert_hash:
                raise ValueError(f"{cid}: scale certificate hash mismatch")
            if cid in terminals:
                raise ValueError(f"duplicate scale case: {cid}")
            terminals[cid] = {
                "terminal_status": "AUDITED_WEIGHTED_ARITHMETIC_CONTRADICTION",
                "source_kind": sid,
                "compact_receipt": source_ref(receipt_path),
                "certificate": source_ref(cert_path),
                "independent_audit": source_ref(audit_path),
            }
    return terminals


def main() -> None:
    structural = json.loads(STRUCTURAL.read_text())
    terminals = load_terminal_sources()
    expected: dict[str, list[str]] = defaultdict(list)
    for formula in structural["formulas"]:
        for terminal in formula["terminal_partition"]:
            if terminal["kind"] != "frontier":
                raise ValueError("unexpected non-frontier terminal in 4,402-cube partition")
            expected[formula["leaf_id"]].append(case_id(formula["leaf_id"], terminal["path"]))
    expected_ids = {cid for ids in expected.values() for cid in ids}
    if len(expected_ids) != 4402 or set(terminals) != expected_ids:
        raise ValueError("terminal source set is not exactly the structural 4,402-cube frontier")

    formula_rows = []
    for formula in structural["formulas"]:
        formula_id = formula["leaf_id"]
        children = [
            {"case_id": cid, **terminals[cid]}
            for cid in sorted(expected[formula_id])
        ]
        receipt = {
            "schema_version": 1,
            "formula_id": formula_id,
            "target_child_id": formula["target_child_id"],
            "structural_manifest": source_ref(STRUCTURAL),
            "frontier_child_count": len(children),
            "children": children,
            "terminal_child_count": len(children),
            "formula_status": "CLOSED_BY_EXHAUSTIVE_WEIGHTED_CHILD_AGGREGATION",
            "claim_limit": "This closes only the exact selected second-live formula. It does not by itself close its target child, fifth leaf, fourth parent, ordinary classification, or C(12,6,4).",
        }
        receipt_path = OUT / "formulas" / f"{formula_id}.json"
        write_json(receipt_path, receipt)
        formula_rows.append({
            "formula_id": formula_id,
            "target_child_id": formula["target_child_id"],
            "frontier_child_count": len(children),
            "receipt": source_ref(receipt_path),
            "status": receipt["formula_status"],
        })

    summary = {
        "schema_version": 1,
        "status": "BUILT_PENDING_INDEPENDENT_AUDIT",
        "bindings": {
            "structural_manifest": source_ref(STRUCTURAL),
            "scale_manifest": source_ref(SCALE),
        },
        "frontier_children_expected": 4402,
        "frontier_children_terminal": len(terminals),
        "source_kind_counts": {
            key: sum(row["source_kind"] == key for row in terminals.values())
            for key in sorted({row["source_kind"] for row in terminals.values()})
        },
        "formula_count": len(formula_rows),
        "formulas_closed": len(formula_rows),
        "formulas": formula_rows,
        "case_ids_sha256": canonical_sha(sorted(terminals)),
        "ancestor_effect": {
            "target_children_closed": 0,
            "fifth_leaves_closed": 0,
            "fourth_parents_closed": 0,
            "ordinary_classification_closed": False,
            "global_extension_ledger_change": 0,
        },
        "claim_limit": "All 4,402 exact depth-two cubes are terminal, closing the 12 selected second-live formulas only. No ancestor closure is asserted without its own exhaustive child aggregation.",
    }
    write_json(OUT / "summary.json", summary)
    print(json.dumps({
        "frontier_children_terminal": len(terminals),
        "formulas_closed": len(formula_rows),
        "source_kind_counts": summary["source_kind_counts"],
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

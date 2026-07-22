#!/usr/bin/env python3
"""Reconcile the complete fourth-level universe, receipts, and open set."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from audit_ordinary_c1153_fourth_split import audit as audit_partition


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "artifacts/classification/ordinary-c1153-v1/hard-tail-fourth-split"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    partition = audit_partition()
    manifest_path = BASE / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    branch_index = {}
    parent_index = {}
    for parent in manifest["parents"]:
        parent_index[parent["id"]] = parent
        for branch in parent["branches"]:
            if branch["id"] in branch_index:
                raise ValueError(f"duplicate manifest branch {branch['id']}")
            branch_index[branch["id"]] = (parent, branch)
    if len(branch_index) != 790 or partition["total_branches"] != 790:
        raise ValueError("fourth-level universe is not exactly 790")

    result_paths = []
    by_campaign = {}
    for campaign in ("discriminator-10s", "suffix-proof-scale-3s"):
        paths = sorted((BASE / campaign).glob("*/result.json"))
        by_campaign[campaign] = paths
        result_paths.extend(paths)
    measured = {}
    for path in result_paths:
        result = json.loads(path.read_text())
        leaf_id = result["leaf_id"]
        if leaf_id not in branch_index:
            raise ValueError(f"result outside manifest: {leaf_id}")
        if leaf_id in measured:
            raise ValueError(f"duplicate measured branch: {leaf_id}")
        measured[leaf_id] = result

    proof_audit_path = BASE / "independent-discriminator-audit.json"
    proof_audit = json.loads(proof_audit_path.read_text())
    audited = {row["id"]: row["status"] for row in proof_audit["results"]}
    expected_audited = {
        leaf_id: "UNSAT_REPLAYED" if result["status"] == "UNSAT_VERIFIED" else "FIXED_CAP_TIMEOUT"
        for leaf_id, result in measured.items()
    }
    if audited != expected_audited:
        raise ValueError("independent proof audit does not exactly match measured receipts")

    discriminator_ids = {json.loads(path.read_text())["leaf_id"] for path in by_campaign["discriminator-10s"]}
    expected_suffix = set()
    for parent in manifest["parents"]:
        midpoint = len(parent["branches"]) // 2
        expected_suffix.update(branch["id"] for branch in parent["branches"][midpoint:] if branch["id"] not in discriminator_ids)
    actual_suffix = {json.loads(path.read_text())["leaf_id"] for path in by_campaign["suffix-proof-scale-3s"]}
    suffix_summary_path = BASE / "suffix-proof-scale-3s-summary.json"
    suffix_summary = json.loads(suffix_summary_path.read_text())
    summary_suffix = {row["leaf_id"] for row in suffix_summary["outcomes"]}
    protocol_path = ROOT / suffix_summary["protocol"]["path"]
    protocol = json.loads(protocol_path.read_text())
    protocol_suffix = set(protocol["leaf_ids"])
    if not (expected_suffix == actual_suffix == summary_suffix == protocol_suffix):
        raise ValueError("suffix selection omission or duplication")

    verified = sorted(leaf_id for leaf_id, result in measured.items() if result["status"] == "UNSAT_VERIFIED")
    timeouts = sorted(leaf_id for leaf_id, result in measured.items() if result["status"] == "FIXED_CAP_TIMEOUT")
    unmeasured = sorted(set(branch_index) - set(measured))
    open_ids = sorted(set(timeouts) | set(unmeasured))
    if (len(verified), len(timeouts), len(unmeasured), len(open_ids)) != (406, 32, 352, 384):
        raise ValueError("fourth-level accounting mismatch")

    open_rows = []
    for leaf_id in open_ids:
        parent, branch = branch_index[leaf_id]
        open_rows.append({
            "id": leaf_id,
            "status": "FIXED_CAP_TIMEOUT" if leaf_id in set(timeouts) else "NEVER_MEASURED",
            "parent_id": parent["id"],
            "top_parent": parent["top_parent"],
            "parent_cnf": parent["parent_cnf"],
            "fixed_blocks": parent["fixed_blocks"] + [branch["canonical_fourth_block"]],
            "fourth_branch": branch,
        })
    open_manifest = {
        "schema_version": 1,
        "status": "AUDITED_OPEN_SET",
        "fourth_manifest": {"path": str(manifest_path.relative_to(ROOT)), "sha256": sha(manifest_path)},
        "proof_audit": {"path": str(proof_audit_path.relative_to(ROOT)), "sha256": sha(proof_audit_path)},
        "counts": {"universe": 790, "replay_verified_unsat": 406, "fixed_cap_timeout": 32, "never_measured": 352, "open": 384},
        "open_cases": open_rows,
        "claim_limit": "Open-set accounting only; no open case is closed by this manifest.",
    }
    open_path = BASE / "open-fourth-level-manifest.json"
    open_path.write_text(json.dumps(open_manifest, indent=2, sort_keys=True) + "\n")
    report = {
        "schema_version": 1,
        "status": "VALID",
        "partition_audit": partition["status"],
        "fourth_manifest_sha256": sha(manifest_path),
        "proof_audit_sha256": sha(proof_audit_path),
        "suffix_protocol_sha256": sha(protocol_path),
        "suffix_summary_sha256": sha(suffix_summary_path),
        "suffix_expected": len(expected_suffix),
        "suffix_actual": len(actual_suffix),
        "duplicate_measured_cases": 0,
        "omitted_selected_suffix_cases": 0,
        "counts": open_manifest["counts"],
        "open_manifest": {"path": str(open_path.relative_to(ROOT)), "sha256": sha(open_path)},
        "correction": "The prior 416-open statement double-counted 32 cases. Exact accounting is 406 closed plus 384 open = 790; the open set is 32 timeouts plus 352 unmeasured.",
    }
    target = BASE / "fourth-level-ledger-audit.json"
    target.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Independently aggregate the completed fifth-level suffix tranche.

This checker keeps solver receipts, replay-certified leaves, and parent closure
separate.  It is intentionally read-only except for its final atomic report.
"""

from __future__ import annotations

import hashlib
import json
import os
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "artifacts/classification/ordinary-c1153-v1/hard-tail-fifth-split"
OUTPUT = BASE / "terminal-aggregate-audit.json"
UNSAT = {"UNSAT_VERIFIED_BY_RUNNER", "PROVISIONAL_UNSAT_PROOF_RETAINED"}


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def load(path: Path) -> dict:
    return json.loads(path.read_text())


def main() -> None:
    fifth_path = BASE / "manifest.json"
    route_path = BASE / "suffix-scale-manifest.json"
    route_audit_path = BASE / "suffix-scale-independent-audit.json"
    discriminator_audit_path = BASE / "independent-discriminator-audit.json"
    certified_ledger_path = BASE / "suffix-certification/certified-ledger.json"
    suffix_ledger_path = BASE / "suffix-scale-ledger.json"
    controller_path = BASE / "controller-0045-0127.json"

    fifth = load(fifth_path)
    route = load(route_path)
    route_audit = load(route_audit_path)
    discriminator_audit = load(discriminator_audit_path)
    certified_ledger = load(certified_ledger_path)
    suffix_ledger = load(suffix_ledger_path)
    controller = load(controller_path)

    assert route_audit["status"] == "VALID"
    assert route_audit["route_manifest_sha256"] == sha(route_path)
    assert discriminator_audit["status"] == "VALID"
    assert controller["status"] == "COMPLETE"
    assert controller["requested_stop"] == 127
    assert controller["ledger_sha256"] == sha(suffix_ledger_path)
    assert controller["totals"] == suffix_ledger["totals"]
    assert suffix_ledger["remaining_unmeasured_scale_jobs"] == 0

    all_children: set[str] = set()
    children_by_parent: dict[str, set[str]] = {}
    for parent in fifth["parents"]:
        children = {
            f"{parent['id']}-fifth-{index:03d}"
            for index in range(parent["branch_count"])
        }
        assert not (all_children & children)
        all_children.update(children)
        children_by_parent[parent["id"]] = children
    assert len(children_by_parent) == 384
    assert len(all_children) == 43_319

    route_ids = [leaf for segment in route["segments"] for leaf in segment["leaf_ids"]]
    assert len(route_ids) == len(set(route_ids)) == 32_597
    assert set(route_ids) <= all_children

    suffix_status: dict[str, str] = {}
    sampled_certified: set[str] = set()
    segment_bindings: list[dict[str, object]] = []
    for number in range(128):
        directory = BASE / "segments" / f"segment-{number:04d}"
        manifest_path = directory / "manifest.json"
        receipt_path = directory / "runner-receipt.json"
        audit_path = directory / "independent-audit.json"
        manifest, receipt, audit = load(manifest_path), load(receipt_path), load(audit_path)
        assert receipt["status"] == "COMPLETE_PENDING_INDEPENDENT_AUDIT"
        assert audit["status"] == "VALID" and audit["continuation_gate_passed"]
        assert receipt["segment_manifest"]["sha256"] == sha(manifest_path)
        assert audit["segment_manifest_sha256"] == sha(manifest_path)
        assert audit["runner_receipt_sha256"] == sha(receipt_path)
        assert manifest["leaf_ids"] == route["segments"][number]["leaf_ids"]
        for leaf_id in manifest["leaf_ids"]:
            result_path = directory / leaf_id / "result.json"
            result = load(result_path)
            assert result["leaf_id"] == leaf_id
            assert leaf_id not in suffix_status
            suffix_status[leaf_id] = result["status"]
        sampled_certified.update(
            row["leaf_id"] for row in audit["results"] if row["status"] == "UNSAT_REPLAYED"
        )
        segment_bindings.append({
            "segment": number,
            "manifest_sha256": sha(manifest_path),
            "runner_receipt_sha256": sha(receipt_path),
            "independent_audit_sha256": sha(audit_path),
        })
    assert set(suffix_status) == set(route_ids)
    suffix_counts = Counter(suffix_status.values())
    assert sum(suffix_counts.values()) == 32_597
    assert sum(suffix_counts[status] for status in UNSAT) == 32_547
    assert suffix_counts["FIXED_CAP_TIMEOUT"] == 50
    assert not any(status.startswith("SAT_") for status in suffix_counts)
    assert len(sampled_certified) == 4_046

    discriminator_status = {
        row["id"]: row["status"] for row in discriminator_audit["results"]
    }
    assert len(discriminator_status) == 96
    assert Counter(discriminator_status.values()) == {
        "UNSAT_REPLAYED": 64,
        "FIXED_CAP_TIMEOUT": 32,
    }
    assert set(discriminator_status) <= all_children
    assert not (set(discriminator_status) & set(suffix_status))

    batch_certified: set[str] = set()
    batch_bindings: list[dict[str, object]] = []
    for batch_dir in sorted((BASE / "suffix-certification/batches").glob("batch-*")):
        batch_receipt_path = batch_dir / "batch-receipt.json"
        if not batch_receipt_path.exists():
            continue
        receipt = load(batch_receipt_path)
        assert receipt["status"] == "COMPLETE"
        case_ids = {
            path.parent.name
            for path in batch_dir.glob("cases/*/receipt.json")
            if load(path)["status"] == "CERTIFIED_UNSAT"
        }
        assert len(case_ids) == receipt["certified_unsat"]
        assert not (batch_certified & case_ids)
        batch_certified.update(case_ids)
        batch_bindings.append({
            "batch_id": receipt["batch_id"],
            "batch_receipt_sha256": sha(batch_receipt_path),
            "certified_unsat": len(case_ids),
        })
    assert len(batch_certified) == 11_264
    assert batch_certified <= {leaf for leaf, status in suffix_status.items() if status in UNSAT}
    assert not (batch_certified & sampled_certified)
    certified_suffix = batch_certified | sampled_certified
    assert len(certified_suffix) == 15_310
    assert certified_ledger["counts"] == {
        "sampled_operational_replay_certificates": 4_046,
        "exhaustive_batch_certificates": 11_264,
        "overlap": 0,
        "distinct_certified_suffix_unsat": 15_310,
    }

    measured = set(suffix_status) | set(discriminator_status)
    certified_fifth = certified_suffix | {
        leaf for leaf, status in discriminator_status.items() if status == "UNSAT_REPLAYED"
    }
    timeout_ids = {
        leaf for leaf, status in suffix_status.items() if status == "FIXED_CAP_TIMEOUT"
    } | {
        leaf for leaf, status in discriminator_status.items() if status == "FIXED_CAP_TIMEOUT"
    }
    unmeasured = all_children - measured
    open_ids = timeout_ids | unmeasured
    complete_parents = [
        parent_id for parent_id, children in children_by_parent.items()
        if children <= certified_fifth
    ]
    assert len(measured) == 32_693
    assert len(unmeasured) == 10_626
    assert len(timeout_ids) == 82
    assert len(open_ids) == 10_708
    assert len(certified_fifth) == 15_374
    assert not complete_parents

    sixth_audit_path = ROOT / "artifacts/classification/ordinary-c1153-v1/hard-tail-sixth-discriminator/independent-audit.json"
    sixth_audit = load(sixth_audit_path)
    assert sixth_audit["status"] == "VALID" and sixth_audit["case_count"] == 48
    frozen_sixth_ids = {row["id"] for row in sixth_audit["cases"]}
    assert frozen_sixth_ids <= timeout_ids
    later_timeouts = timeout_ids - frozen_sixth_ids
    assert len(later_timeouts) == 34

    report = {
        "schema_version": 1,
        "status": "VALID",
        "bindings": {
            "fifth_manifest_sha256": sha(fifth_path),
            "suffix_route_sha256": sha(route_path),
            "suffix_route_audit_sha256": sha(route_audit_path),
            "discriminator_audit_sha256": sha(discriminator_audit_path),
            "certified_ledger_sha256": sha(certified_ledger_path),
            "suffix_ledger_sha256": sha(suffix_ledger_path),
            "suffix_controller_sha256": sha(controller_path),
            "sixth_snapshot_audit_sha256": sha(sixth_audit_path),
            "segments": segment_bindings,
            "certification_batches": batch_bindings,
        },
        "counts": {
            "fifth_branches_total": len(all_children),
            "measured_distinct": len(measured),
            "solver_or_replay_unsat_distinct": 32_611,
            "certified_unsat_distinct": len(certified_fifth),
            "provisional_unsat_backlog": 32_611 - len(certified_fifth),
            "timeouts": len(timeout_ids),
            "never_measured": len(unmeasured),
            "open_distinct": len(open_ids),
            "complete_fourth_parents": len(complete_parents),
            "sat": 0,
        },
        "suffix": {
            "selected": 32_597,
            "provisional_solver_unsat": 32_547,
            "timeouts": 50,
            "sampled_replay_certified": 4_046,
            "bulk_replay_certified": 11_264,
            "distinct_replay_certified": 15_310,
        },
        "hard_tail": {
            "audited_sixth_snapshot_timeouts": len(frozen_sixth_ids),
            "later_timeouts_requiring_fresh_manifest": len(later_timeouts),
            "final_timeout_total": len(timeout_ids),
            "later_timeout_ids_sha256": hashlib.sha256(
                ("\n".join(sorted(later_timeouts)) + "\n").encode()
            ).hexdigest(),
        },
        "claim_limit": (
            "The suffix harvest is fully measured, but 17,237 suffix UNSAT proofs await exhaustive "
            "replay, 82 measured leaves timed out, 10,626 fifth leaves were intentionally not measured, "
            "and no fourth-level parent is closed."
        ),
    }
    payload = (json.dumps(report, indent=2, sort_keys=True) + "\n").encode()
    temporary = OUTPUT.with_suffix(".json.tmp")
    temporary.write_bytes(payload)
    os.replace(temporary, OUTPUT)
    print(json.dumps(report["counts"], indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

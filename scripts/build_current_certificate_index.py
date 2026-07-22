#!/usr/bin/env python3
"""Build the complete hash-bound durable certificate index for the active ledger."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "checkers"))
from verify_certificate_portfolio import verify  # noqa: E402


MANIFEST = Path("artifacts/portfolio/frontier-manifest-v1.json")
OUTPUT = Path("artifacts/classification/exhaustive-link-v1/certificate-index-32of47.json")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def checked_receipt(value: dict[str, str]) -> dict[str, object]:
    path = ROOT / value["path"]
    if not path.is_file() or sha(path) != value["sha256"]:
        raise ValueError(f"invalid receipt: {value['path']}")
    return {"path": value["path"], "sha256": value["sha256"], "bytes": path.stat().st_size}


def build() -> dict[str, object]:
    manifest_path = ROOT / MANIFEST
    verify(manifest_path)
    manifest = json.loads(manifest_path.read_text())
    certificates = []
    for node in manifest["nodes"]:
        if node["final_coverage_status"] != "closed_unsat":
            continue
        outcomes = [row for row in node["outcomes"] if row.get("status") == "unsat_certified"]
        if not outcomes:
            raise ValueError(f"closed node lacks certified outcome: {node['id']}")
        rows = []
        for outcome in outcomes:
            row = {
                "run_id": outcome["run_id"],
                "method": outcome["method"],
                "cnf_sha256": outcome["cnf_sha256"],
                "proof_sha256": outcome["proof_sha256"],
                "result_receipt": checked_receipt(outcome["result_receipt"]),
                "cnf_audit_receipt": checked_receipt(outcome["independent_audit_receipt"]),
                "replay_receipt": checked_receipt(outcome["replay_receipt"]),
            }
            if outcome.get("post_tranche_independent_replay_receipt"):
                row["post_tranche_independent_replay_receipt"] = checked_receipt(
                    outcome["post_tranche_independent_replay_receipt"]
                )
            rows.append(row)
        certificates.append({"id": node["id"], "active_blocker_sha256": node["active_blocker_sha256"],
                             "certified_outcomes": rows})
    certificates.sort(key=lambda row: row["id"])
    if len(certificates) != 32 or manifest["counts"] != {"total": 47, "closed": 32, "open": 15}:
        raise ValueError("expected the audited 32/47 ledger")

    incident_path = ROOT / "artifacts/experiments/link-orbit-t-16-extension-300s-20260722/PROOF-INCIDENT.json"
    t16_validation = ROOT / "artifacts/experiments/link-orbit-t-16-extension-300s-20260722/independent-validation.json"
    t17_validation = ROOT / "artifacts/experiments/link-orbit-t-17-extension-300s-20260722/independent-validation.json"
    incident = json.loads(incident_path.read_text())
    valid16, valid17 = (json.loads(path.read_text()) for path in (t16_validation, t17_validation))
    if incident["status"] != "superseded_invalid_proof":
        raise ValueError("t-16 proof incident status changed")
    if valid16["proof"]["sha256"] != incident["replacement_external_proof_sha256"]:
        raise ValueError("t-16 validation does not use the external replacement proof")
    if valid16["proof"]["sha256"] == incident["rejected_proof_sha256"]:
        raise ValueError("t-16 validation incorrectly uses the rejected proof")
    if any(value["status"] != "verified_unsat_fixed_link_extension" for value in (valid16, valid17)):
        raise ValueError("new-orbit extension validation missing")

    return {
        "schema_version": 1,
        "status": "valid",
        "manifest": {"path": str(MANIFEST), "sha256": sha(manifest_path),
                     "payload_sha256": manifest["manifest_payload_sha256"]},
        "frontier_definition_sha256": manifest["frontier_definition_sha256"],
        "frontier_source": manifest["frontier_source"],
        "active_link_blocker": manifest["active_link_blocker"],
        "counts": {"frontier_nodes": 47, "durable_certificates": len(certificates), "open": 15},
        "closed_node_ids": [row["id"] for row in certificates],
        "certificates": certificates,
        "new_orbit_extension_evidence": {
            "claim_limit": "Residual nonextension receipts do not close t-16 or t-17 frontier leaves.",
            "t-16_incident": {"path": str(incident_path.relative_to(ROOT)), "sha256": sha(incident_path)},
            "t-16_valid_external_replacement": {"path": str(t16_validation.relative_to(ROOT)), "sha256": sha(t16_validation)},
            "t-17_valid_replay": {"path": str(t17_validation.relative_to(ROOT)), "sha256": sha(t17_validation)},
        },
        "claim_limit": "Complete receipt index for the current 32/47 ledger; it does not prove catalogue exhaustion.",
    }


def main() -> None:
    value = build()
    output = ROOT / OUTPUT
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    print(f"indexed {value['counts']['durable_certificates']} durable closures")


if __name__ == "__main__":
    main()

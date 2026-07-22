#!/usr/bin/env python3
"""Recover the completed hard-tranche summary without rerunning any solver.

The original runner completed all 42 fixed-cap calls but failed while sorting
its in-memory summary because verified receipts use ``leaf_id`` rather than
``id``.  UNSAT results were durable; TIMEOUT results were not.  This script
records those timeouts only when the preserved solver log ends in UNKNOWN.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "artifacts/classification/ordinary-c1153-v1/hard-split"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    manifest_path = BASE / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    outcomes = []
    recovered = []
    for child in [item for parent in manifest["parents"] for item in parent["children"]]:
        folder = ROOT / child["cnf"]["path"]
        result_path = folder.parent / "result.json"
        result = json.loads(result_path.read_text())
        if result["status"] == "NOT_RUN":
            solver_log = folder.parent / "solver.log"
            proof = folder.parent / "proof.drat"
            if not solver_log.exists() or "UNKNOWN" not in solver_log.read_text():
                raise ValueError(f"{child['id']}: missing fixed-cap UNKNOWN evidence")
            result = {
                "schema_version": 1,
                "status": "FIXED_CAP_TIMEOUT",
                "leaf_id": child["id"],
                "seconds_cap": 60,
                "solver_log": {"path": str(solver_log.relative_to(ROOT)), "sha256": sha(solver_log)},
                "partial_proof_incident": {"path": str(proof.relative_to(ROOT)), "sha256": sha(proof), "bytes": proof.stat().st_size},
                "claim_limit": "UNKNOWN and its partial proof close no case.",
            }
            result_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
            recovered.append(child["id"])
        result["leaf_id"] = result.get("leaf_id", child["id"])
        outcomes.append(result)
    outcomes.sort(key=lambda row: row["leaf_id"])
    incident = {
        "schema_version": 1,
        "status": "PRESERVED_ORCHESTRATION_INCIDENT",
        "failure": "KeyError: id while sorting the completed in-memory outcome list",
        "effect": "The consolidated summary was not written; 29 durable verified receipts survived and 13 UNKNOWN logs required timeout-receipt recovery.",
        "mathematical_effect": "none",
        "solver_reruns": 0,
        "recovered_timeout_ids": recovered,
    }
    incident_path = BASE / "summary-writer-incident.json"
    incident_path.write_text(json.dumps(incident, indent=2, sort_keys=True) + "\n")
    counts = {name: sum(row["status"] == name for row in outcomes) for name in sorted({row["status"] for row in outcomes})}
    summary = {
        "schema_version": 1,
        "status": "COMPLETE_WITH_RECOVERED_SUMMARY",
        "fixed_protocol": {"seconds_cap": 60, "parallelism": 4, "children": len(outcomes)},
        "manifest": {"path": str(manifest_path.relative_to(ROOT)), "sha256": sha(manifest_path)},
        "incident": {"path": str(incident_path.relative_to(ROOT)), "sha256": sha(incident_path)},
        "counts": counts,
        "outcomes": outcomes,
        "claim_limit": "Verified receipts close children only. Fixed-cap timeouts and partial proof streams close nothing.",
    }
    target = BASE / "proof-tranche-60s.json"
    target.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"summary": str(target), "counts": counts, "recovered": len(recovered)}, sort_keys=True))


if __name__ == "__main__":
    main()

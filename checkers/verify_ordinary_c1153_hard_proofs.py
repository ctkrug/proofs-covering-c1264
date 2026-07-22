#!/usr/bin/env python3
"""Independent replay and ingestion audit for the ordinary C(11,5,3) hard split."""

from __future__ import annotations

import hashlib
import json
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from audit_ordinary_c1153_hard_split import audit as audit_partition


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "artifacts/classification/ordinary-c1153-v1/hard-split"
CHECKER = ROOT / ".venv/sat-audit-tools/drat-trim/drat-trim"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def replay(child: dict[str, object]) -> dict[str, object]:
    cnf = ROOT / child["cnf"]["path"]
    result_path = ROOT / child["result"]["path"]
    result = json.loads(result_path.read_text())
    status = result["status"]
    if sha(cnf) != child["cnf"]["sha256"]:
        raise ValueError(f"{child['id']}: CNF hash mismatch")
    if status == "FIXED_CAP_TIMEOUT":
        log = ROOT / result["solver_log"]["path"]
        partial = ROOT / result["partial_proof_incident"]["path"]
        if sha(log) != result["solver_log"]["sha256"] or "UNKNOWN" not in log.read_text():
            raise ValueError(f"{child['id']}: timeout log audit failed")
        if sha(partial) != result["partial_proof_incident"]["sha256"]:
            raise ValueError(f"{child['id']}: partial proof incident hash mismatch")
        return {"id": child["id"], "status": status}
    if status != "UNSAT_VERIFIED":
        raise ValueError(f"{child['id']}: unaudited status {status}")
    receipt_path = ROOT / result["replay_receipt"]["path"]
    if sha(receipt_path) != result["replay_receipt"]["sha256"]:
        raise ValueError(f"{child['id']}: receipt hash mismatch")
    receipt = json.loads(receipt_path.read_text())
    proof = ROOT / receipt["proof"]["path"]
    if receipt["leaf_id"] != child["id"] or receipt["cnf"]["sha256"] != child["cnf"]["sha256"]:
        raise ValueError(f"{child['id']}: receipt binding mismatch")
    if sha(proof) != receipt["proof"]["sha256"]:
        raise ValueError(f"{child['id']}: proof hash mismatch")
    checked = subprocess.run([str(CHECKER), str(cnf), str(proof)], capture_output=True, text=True, timeout=600)
    if checked.returncode != 0 or "VERIFIED" not in checked.stdout + checked.stderr:
        raise ValueError(f"{child['id']}: independent replay failed")
    return {"id": child["id"], "status": "UNSAT_REPLAYED", "proof_sha256": sha(proof)}


def main() -> None:
    partition = audit_partition()
    manifest_path = BASE / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    children = [child for parent in manifest["parents"] for child in parent["children"]]
    rows = []
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(replay, child): child["id"] for child in children}
        for future in as_completed(futures):
            rows.append(future.result())
    rows.sort(key=lambda row: row["id"])
    by_parent = {}
    for parent in manifest["parents"]:
        ids = {child["id"] for child in parent["children"]}
        parent_rows = [row for row in rows if row["id"] in ids]
        verified = sum(row["status"] == "UNSAT_REPLAYED" for row in parent_rows)
        by_parent[parent["id"]] = {"verified_children": verified, "children": len(ids), "parent_closed": verified == len(ids)}
    report = {
        "schema_version": 1,
        "status": "VALID",
        "partition_audit_status": partition["status"],
        "manifest_sha256": sha(manifest_path),
        "checker": {"path": str(CHECKER.relative_to(ROOT)), "sha256": sha(CHECKER)},
        "counts": {"UNSAT_REPLAYED": sum(row["status"] == "UNSAT_REPLAYED" for row in rows), "FIXED_CAP_TIMEOUT": sum(row["status"] == "FIXED_CAP_TIMEOUT" for row in rows)},
        "parents": by_parent,
        "results": rows,
        "classification_complete": all(row["parent_closed"] for row in by_parent.values()),
        "claim_limit": "This audits the two hard top-level branches only; ordinary uniqueness also requires the three easy top-level certificates.",
    }
    target = BASE / "independent-proof-audit.json"
    target.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    main()

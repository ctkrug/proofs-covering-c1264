#!/usr/bin/env python3
"""Independently reconstruct and replay the fourth-split discriminator."""

from __future__ import annotations

import gzip
import hashlib
import json
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from pysat.formula import CNF

from audit_ordinary_c1153_fourth_split import audit as audit_partition


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "artifacts/classification/ordinary-c1153-v1/hard-tail-fourth-split"
CHECKER = ROOT / ".venv/sat-audit-tools/drat-trim/drat-trim"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def replay(parent: dict[str, object], branch: dict[str, object], result: dict[str, object]) -> dict[str, object]:
    if result["status"] == "FIXED_CAP_TIMEOUT":
        return {"id": branch["id"], "status": "FIXED_CAP_TIMEOUT"}
    if result["status"] != "UNSAT_VERIFIED":
        raise ValueError(f"{branch['id']}: unsupported status {result['status']}")
    parent_path = ROOT / parent["parent_cnf"]["path"]
    assumptions = [-value for value in branch["earlier_fourth_variables_forced_false"]] + [branch["canonical_fourth_block_variable"]]
    exact = CNF(from_file=str(parent_path))
    exact = CNF(from_clauses=exact.clauses + [[value] for value in assumptions])
    compressed = ROOT / result["proof"]["path"]
    if sha(compressed) != result["proof"]["sha256"]:
        raise ValueError(f"{branch['id']}: compressed proof hash mismatch")
    with tempfile.TemporaryDirectory(prefix="ordinary-fourth-audit-") as temporary:
        temp = Path(temporary)
        cnf_path = temp / "instance.cnf"
        proof_path = temp / "proof.drat"
        exact.to_file(str(cnf_path))
        if sha(cnf_path) != result["exact_cnf_sha256"]:
            raise ValueError(f"{branch['id']}: exact CNF reconstruction hash mismatch")
        with gzip.open(compressed, "rb") as source, proof_path.open("wb") as target:
            while chunk := source.read(1024 * 1024):
                target.write(chunk)
        if sha(proof_path) != result["proof"]["uncompressed_sha256"]:
            raise ValueError(f"{branch['id']}: uncompressed proof hash mismatch")
        checked = subprocess.run([str(CHECKER), str(cnf_path), str(proof_path)], capture_output=True, text=True, timeout=600)
        if checked.returncode != 0 or "VERIFIED" not in checked.stdout + checked.stderr:
            raise ValueError(f"{branch['id']}: replay failed")
    return {"id": branch["id"], "status": "UNSAT_REPLAYED", "exact_cnf_sha256": result["exact_cnf_sha256"], "proof_sha256": result["proof"]["sha256"]}


def main() -> None:
    partition = audit_partition()
    manifest = json.loads((BASE / "manifest.json").read_text())
    summary_paths = [BASE / "discriminator-10s-summary.json", BASE / "boundary-10s-summary.json", BASE / "suffix-proof-scale-3s-summary.json"]
    branch_index = {branch["id"]: (parent, branch) for parent in manifest["parents"] for branch in parent["branches"]}
    jobs = []
    for campaign in ("discriminator-10s", "suffix-proof-scale-3s"):
        for result_path in sorted((BASE / campaign).glob("*/result.json")):
            result = json.loads(result_path.read_text())
            parent, branch = branch_index[result["leaf_id"]]
            jobs.append((parent, branch, result))
    rows = []
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(replay, *job) for job in jobs]
        for future in as_completed(futures):
            rows.append(future.result())
    rows.sort(key=lambda row: row["id"])
    report = {
        "schema_version": 1,
        "status": "VALID",
        "partition_audit_status": partition["status"],
        "summary_sha256": {path.name: sha(path) for path in summary_paths},
        "checker_sha256": sha(CHECKER),
        "counts": {"UNSAT_REPLAYED": sum(row["status"] == "UNSAT_REPLAYED" for row in rows), "FIXED_CAP_TIMEOUT": sum(row["status"] == "FIXED_CAP_TIMEOUT" for row in rows)},
        "results": rows,
        "claim_limit": "These replayed certificates close only their measured fourth-split branches.",
    }
    target = BASE / "independent-discriminator-audit.json"
    target.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    main()

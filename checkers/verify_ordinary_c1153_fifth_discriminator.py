#!/usr/bin/env python3
"""Independent reconstruction, selection audit, and proof replay for fifth sample."""

from __future__ import annotations

import gzip
import hashlib
import json
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from pysat.formula import CNF

from audit_ordinary_c1153_fifth_split import audit as audit_partition


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "artifacts/classification/ordinary-c1153-v1/hard-tail-fifth-split"
CHECKER = ROOT / ".venv/sat-audit-tools/drat-trim/drat-trim"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def unit_sha(units: list[int]) -> str:
    return hashlib.sha256((" ".join(map(str, units)) + "\n").encode()).hexdigest()


def expected_parent_ids(manifest: dict[str, object]) -> set[str]:
    groups = {}
    for parent in manifest["parents"]:
        groups.setdefault((parent["prior_status"], parent["top_parent"]), []).append(parent)
    chosen = set()
    for rows in groups.values():
        rows = sorted(rows, key=lambda row: (row["branch_count"], row["id"]))
        positions = {round(step * (len(rows) - 1) / 5) for step in range(6)}
        if len(positions) != 6:
            raise ValueError("independent stratum quantiles collapsed")
        chosen.update(rows[index]["id"] for index in positions)
    return chosen


def replay(parent: dict[str, object], sample: dict[str, object], result: dict[str, object]) -> dict[str, object]:
    index = sample["index"]
    earlier = [value for orbit in parent["fifth_orbits"][:index] for value in orbit["member_variables"]]
    fifth_units = [-value for value in earlier] + [parent["fifth_orbits"][index]["canonical_variable"]]
    if unit_sha(fifth_units) != result["fifth_unit_sha256"]:
        raise ValueError(f"{sample['leaf_id']}: fifth recipe mismatch")
    parent_path = ROOT / parent["third_level_parent_cnf"]["path"]
    base = CNF(from_file=str(parent_path))
    exact = CNF(from_clauses=base.clauses + [[value] for value in parent["inherited_fourth_units"] + fifth_units])
    if result["status"] == "FIXED_CAP_TIMEOUT":
        log = ROOT / result["solver_log"]["path"]
        if sha(log) != result["solver_log"]["sha256"] or "UNKNOWN" not in log.read_text():
            raise ValueError(f"{sample['leaf_id']}: timeout log mismatch")
        return {"id": sample["leaf_id"], "position": sample["position"], "status": "FIXED_CAP_TIMEOUT"}
    if result["status"] != "UNSAT_VERIFIED":
        raise ValueError(f"{sample['leaf_id']}: unsupported status {result['status']}")
    compressed = ROOT / result["proof"]["path"]
    if sha(compressed) != result["proof"]["sha256"]:
        raise ValueError(f"{sample['leaf_id']}: compressed proof mismatch")
    with tempfile.TemporaryDirectory(prefix="ordinary-fifth-audit-") as temporary:
        temp = Path(temporary)
        cnf_path = temp / "instance.cnf"
        proof_path = temp / "proof.drat"
        exact.to_file(str(cnf_path))
        if sha(cnf_path) != result["exact_cnf_sha256"]:
            raise ValueError(f"{sample['leaf_id']}: reconstructed CNF mismatch")
        with gzip.open(compressed, "rb") as source, proof_path.open("wb") as target:
            while chunk := source.read(1024 * 1024):
                target.write(chunk)
        if sha(proof_path) != result["proof"]["uncompressed_sha256"]:
            raise ValueError(f"{sample['leaf_id']}: uncompressed proof mismatch")
        checked = subprocess.run([str(CHECKER), str(cnf_path), str(proof_path)], capture_output=True, text=True, timeout=600)
        if checked.returncode != 0 or "VERIFIED" not in checked.stdout + checked.stderr:
            raise ValueError(f"{sample['leaf_id']}: independent replay failed")
    return {"id": sample["leaf_id"], "position": sample["position"], "status": "UNSAT_REPLAYED", "proof_sha256": result["proof"]["sha256"], "compressed_bytes": result["proof"]["compressed_bytes"]}


def main() -> None:
    partition = audit_partition()
    manifest_path = BASE / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    protocol_path = BASE / "discriminator-5s-protocol.json"
    protocol = json.loads(protocol_path.read_text())
    summary_path = BASE / "discriminator-5s-summary.json"
    summary = json.loads(summary_path.read_text())
    parent_by_id = {parent["id"]: parent for parent in manifest["parents"]}
    samples = protocol["sample"]
    if len(samples) != 96 or len({row["leaf_id"] for row in samples}) != 96:
        raise ValueError("sample is not 96 unique leaves")
    if {row["parent_id"] for row in samples} != expected_parent_ids(manifest):
        raise ValueError("stratified parent selection mismatch")
    expected_positions = {"orbit_zero": 0, "orbit_one": 1}
    for row in samples:
        parent = parent_by_id[row["parent_id"]]
        expected = expected_positions.get(row["position"], parent["branch_count"] // (4 if row["position"] == "first_quartile" else 2))
        if row["index"] != expected:
            raise ValueError(f"{row['leaf_id']}: position index mismatch")
    result_paths = sorted((BASE / "discriminator-5s").glob("*/result.json"))
    results = {json.loads(path.read_text())["leaf_id"]: json.loads(path.read_text()) for path in result_paths}
    if set(results) != {row["leaf_id"] for row in samples} or len(result_paths) != len(results):
        raise ValueError("result/sample omission or duplication")
    rows = []
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(replay, parent_by_id[sample["parent_id"]], sample, results[sample["leaf_id"]]) for sample in samples]
        for future in as_completed(futures):
            rows.append(future.result())
    rows.sort(key=lambda row: row["id"])
    suffix = [row for row in rows if row["position"] in ("first_quartile", "midpoint")]
    suffix_verified = [row for row in suffix if row["status"] == "UNSAT_REPLAYED"]
    early = [row for row in rows if row["position"] in ("orbit_zero", "orbit_one")]
    compressed_total = sum(row.get("compressed_bytes", 0) for row in rows)
    report = {
        "schema_version": 1,
        "status": "VALID",
        "partition_audit_status": partition["status"],
        "manifest_sha256": sha(manifest_path),
        "protocol_sha256": sha(protocol_path),
        "summary_sha256": sha(summary_path),
        "checker_sha256": sha(CHECKER),
        "sample_size": len(rows),
        "counts": {"UNSAT_REPLAYED": sum(row["status"] == "UNSAT_REPLAYED" for row in rows), "FIXED_CAP_TIMEOUT": sum(row["status"] == "FIXED_CAP_TIMEOUT" for row in rows)},
        "counts_by_position": {position: {"UNSAT_REPLAYED": sum(row["position"] == position and row["status"] == "UNSAT_REPLAYED" for row in rows), "FIXED_CAP_TIMEOUT": sum(row["position"] == position and row["status"] == "FIXED_CAP_TIMEOUT" for row in rows)} for position in ("orbit_zero", "orbit_one", "first_quartile", "midpoint")},
        "compressed_proof_bytes": compressed_total,
        "mean_suffix_compressed_proof_bytes": sum(row["compressed_bytes"] for row in suffix_verified) / len(suffix_verified),
        "scale_gate_passed": len(suffix_verified) >= 39 and sum(row["compressed_bytes"] for row in suffix_verified) / len(suffix_verified) <= 1024 * 1024 and compressed_total <= 64 * 1024 * 1024,
        "early_deeper_split_trigger": sum(row["status"] == "FIXED_CAP_TIMEOUT" for row in early) >= 36,
        "results": rows,
        "claim_limit": "The sample closes 64 exact fifth branches only; no fourth parent or ordinary top-level branch is closed.",
    }
    target = BASE / "independent-discriminator-audit.json"
    target.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({key: report[key] for key in ("status", "counts", "counts_by_position", "compressed_proof_bytes", "mean_suffix_compressed_proof_bytes", "scale_gate_passed", "early_deeper_split_trigger", "claim_limit")}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

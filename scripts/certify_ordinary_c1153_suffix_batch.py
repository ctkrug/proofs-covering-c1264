#!/usr/bin/env python3
"""Resumable exhaustive replay batches for the ordinary-cover suffix harvest.

This is deliberately separate from the sampled operational-QA ledger.  A case
enters this pipeline only from a completed, QA-passed immutable solver segment;
it becomes certified only after exact reconstruction, both proof hash checks,
and an external drat-trim replay.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "artifacts/classification/ordinary-c1153-v1/hard-tail-fifth-split"
CERT_BASE = BASE / "suffix-certification"
CHECKER = ROOT / ".venv/sat-audit-tools/drat-trim/drat-trim"
UNSAT_STATUSES = {"UNSAT_VERIFIED_BY_RUNNER", "PROVISIONAL_UNSAT_PROOF_RETAINED"}


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def json_bytes(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()


def atomic_create(path: Path, value: object) -> None:
    """Create an immutable JSON receipt; accept only an identical prior file."""
    payload = json_bytes(value)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != payload:
            raise ValueError(f"immutable receipt disagreement: {path}")
        return
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    with temporary.open("xb") as target:
        target.write(payload)
        target.flush()
        os.fsync(target.fileno())
    try:
        os.link(temporary, path)
    except FileExistsError:
        if path.read_bytes() != payload:
            raise ValueError(f"concurrent immutable receipt disagreement: {path}")
    finally:
        temporary.unlink(missing_ok=True)


def unit_sha(units: list[int]) -> str:
    return hashlib.sha256((" ".join(map(str, units)) + "\n").encode()).hexdigest()


def fifth_units(parent: dict[str, Any], index: int) -> list[int]:
    earlier = [value for orbit in parent["fifth_orbits"][:index] for value in orbit["member_variables"]]
    return [-value for value in earlier] + [parent["fifth_orbits"][index]["canonical_variable"]]


def write_exact_cnf(parent_path: Path, units: list[int], target: Path) -> tuple[int, int]:
    """Stream a cached parent plus units, byte-identically to PySAT CNF.to_file."""
    with parent_path.open("rb") as source, target.open("wb") as output:
        header = source.readline().split()
        if header[:2] != [b"p", b"cnf"] or len(header) != 4:
            raise ValueError(f"bad cached parent CNF header: {parent_path}")
        variables, clauses = int(header[2]), int(header[3])
        output.write(f"p cnf {variables} {clauses + len(units)}\n".encode())
        shutil.copyfileobj(source, output, length=1024 * 1024)
        output.write(b"".join(f"{value} 0\n".encode() for value in units))
    return variables, clauses + len(units)


def load_domain() -> tuple[dict[str, Any], dict[str, tuple[dict[str, Any], int]]]:
    route_path = BASE / "suffix-scale-manifest.json"
    route = json.loads(route_path.read_text())
    audit_path = BASE / "suffix-scale-independent-audit.json"
    audit = json.loads(audit_path.read_text())
    if audit["status"] != "VALID" or audit["route_manifest_sha256"] != sha(route_path):
        raise ValueError("suffix selection audit binding failed")
    fifth_path = ROOT / route["fifth_manifest"]["path"]
    if sha(fifth_path) != route["fifth_manifest"]["sha256"]:
        raise ValueError("fifth-level manifest binding failed")
    fifth = json.loads(fifth_path.read_text())
    lookup = {
        f"{parent['id']}-fifth-{index:03d}": (parent, index)
        for parent in fifth["parents"] for index in range(parent["branch_count"])
    }
    return route, lookup


def sampled_certified_ids() -> set[str]:
    certified: set[str] = set()
    for path in sorted((BASE / "segments").glob("segment-*/independent-audit.json")):
        audit = json.loads(path.read_text())
        if audit.get("status") != "VALID":
            continue
        certified.update(row["leaf_id"] for row in audit.get("results", []) if row["status"] == "UNSAT_REPLAYED")
    return certified


def batch_certified_ids() -> set[str]:
    return {path.parent.name for path in CERT_BASE.glob("batches/batch-*/cases/*/receipt.json")
            if json.loads(path.read_text()).get("status") == "CERTIFIED_UNSAT"}


def eligible_results(lookup: dict[str, tuple[dict[str, Any], int]]) -> list[dict[str, Any]]:
    """Return only results bound to completed, QA-passed segment snapshots."""
    rows: list[dict[str, Any]] = []
    for segment_dir in sorted((BASE / "segments").glob("segment-*")):
        manifest_path = segment_dir / "manifest.json"
        runner_path = segment_dir / "runner-receipt.json"
        audit_path = segment_dir / "independent-audit.json"
        if not (manifest_path.exists() and runner_path.exists() and audit_path.exists()):
            continue
        manifest, runner, audit = (json.loads(path.read_text()) for path in (manifest_path, runner_path, audit_path))
        if runner.get("status") != "COMPLETE_PENDING_INDEPENDENT_AUDIT":
            continue
        if audit.get("status") != "VALID" or not audit.get("continuation_gate_passed"):
            continue
        if runner["segment_manifest"]["sha256"] != sha(manifest_path):
            raise ValueError(f"segment runner binding failed: {segment_dir.name}")
        if audit["segment_manifest_sha256"] != sha(manifest_path) or audit["runner_receipt_sha256"] != sha(runner_path):
            raise ValueError(f"segment independent-audit binding failed: {segment_dir.name}")
        expected = manifest["leaf_ids"][:runner["completed"]]
        for leaf_id in expected:
            result_path = segment_dir / leaf_id / "result.json"
            if not result_path.exists():
                raise ValueError(f"missing completed result: {leaf_id}")
            result = json.loads(result_path.read_text())
            if result.get("status") not in UNSAT_STATUSES:
                continue
            if leaf_id not in lookup or result["leaf_id"] != leaf_id:
                raise ValueError(f"result/domain identity mismatch: {leaf_id}")
            rows.append({
                "leaf_id": leaf_id,
                "segment": manifest["segment"],
                "result_path": str(result_path.relative_to(ROOT)),
                "result_sha256": sha(result_path),
                "segment_manifest_sha256": sha(manifest_path),
                "runner_receipt_sha256": sha(runner_path),
                "operational_audit_sha256": sha(audit_path),
                "exact_cnf_sha256": result["exact_cnf_sha256"],
                "proof_sha256": result["proof"]["sha256"],
                "raw_proof_sha256": result["proof"]["uncompressed_sha256"],
                "parent_id": result["fourth_parent_id"],
            })
    return rows


def make_manifest(batch_id: int, limit: int, parallelism: int) -> tuple[Path, dict[str, Any]]:
    path = CERT_BASE / "batches" / f"batch-{batch_id:04d}" / "manifest.json"
    if path.exists():
        manifest = json.loads(path.read_text())
        if (manifest.get("batch_id") != batch_id
                or manifest.get("route_manifest_sha256") != sha(BASE / "suffix-scale-manifest.json")
                or manifest.get("checker", {}).get("sha256") != sha(CHECKER)):
            raise ValueError(f"incompatible frozen batch manifest: {path}")
        # Limits and worker count are protocol, not restart-time tuning knobs.
        if manifest["selection"]["limit"] != limit or manifest["parallelism"] != parallelism:
            raise ValueError("restart arguments disagree with the immutable batch manifest")
        return path, manifest
    route, lookup = load_domain()
    already = sampled_certified_ids() | batch_certified_ids()
    candidates = [row for row in eligible_results(lookup) if row["leaf_id"] not in already]
    # A binding is safely deduplicable only if both the exact CNF and compressed/raw
    # proof bytes agree.  Distinct leaf IDs retain distinct receipts.
    primary_for: dict[tuple[str, str, str], str] = {}
    for row in candidates:
        binding = (row["exact_cnf_sha256"], row["proof_sha256"], row["raw_proof_sha256"])
        row["dedup_primary_leaf_id"] = primary_for.setdefault(binding, row["leaf_id"])
    candidates.sort(key=lambda row: (row["segment"], row["leaf_id"]))
    selected = candidates[:limit]
    parent_cache: dict[str, dict[str, Any]] = {}
    for row in selected:
        parent, _ = lookup[row["leaf_id"]]
        if parent["id"] in parent_cache:
            continue
        parent_path = ROOT / parent["third_level_parent_cnf"]["path"]
        observed = sha(parent_path)
        if observed != parent["third_level_parent_cnf"]["sha256"]:
            raise ValueError(f"cached parent CNF mismatch: {parent['id']}")
        with parent_path.open("rb") as source:
            header = source.readline().decode().strip()
        parent_cache[parent["id"]] = {
            "path": str(parent_path.relative_to(ROOT)), "sha256": observed,
            "bytes": parent_path.stat().st_size, "header": header,
        }
    manifest = {
        "schema_version": 1,
        "status": "FROZEN_NOT_RUN",
        "batch_id": batch_id,
        "route_manifest_sha256": sha(BASE / "suffix-scale-manifest.json"),
        "checker": {"path": str(CHECKER.relative_to(ROOT)), "sha256": sha(CHECKER)},
        "selection": {
            "rule": "Earliest completed QA-passed segment order, excluding every already independently replayed leaf.",
            "eligible_at_freeze": len(candidates), "selected": len(selected), "limit": limit,
        },
        "parallelism": parallelism,
        "parent_cnf_cache": parent_cache,
        "cases": selected,
        "claim_limit": "No selected case is certified by this manifest; certification requires its immutable per-case receipt and the completed batch receipt.",
    }
    atomic_create(path, manifest)
    return path, manifest


def verify_parent_cache(manifest: dict[str, Any]) -> dict[str, str]:
    """Hash each shared parent once per batch, not once per child replay."""
    verified: dict[str, str] = {}
    for parent_id, cached in manifest["parent_cnf_cache"].items():
        path = ROOT / cached["path"]
        observed = sha(path)
        if observed != cached["sha256"] or path.stat().st_size != cached["bytes"]:
            raise ValueError(f"batch parent cache disagreement: {parent_id}")
        with path.open("rb") as source:
            if source.readline().decode().strip() != cached["header"]:
                raise ValueError(f"batch parent header disagreement: {parent_id}")
        verified[parent_id] = observed
    return verified


def validate_resumable_receipt(path: Path, case: dict[str, Any], manifest_sha: str) -> dict[str, Any] | None:
    if not path.exists():
        return None
    receipt = json.loads(path.read_text())
    if (receipt.get("status") != "CERTIFIED_UNSAT" or receipt.get("leaf_id") != case["leaf_id"]
            or receipt.get("batch_manifest_sha256") != manifest_sha
            or receipt.get("source_result_sha256") != case["result_sha256"]):
        raise ValueError(f"incompatible resumable certification receipt: {path}")
    return receipt


def certify_one(case: dict[str, Any], lookup: dict[str, tuple[dict[str, Any], int]], batch_dir: Path,
                manifest_sha: str, primary_receipts: dict[str, dict[str, Any]],
                verified_parent_hashes: dict[str, str]) -> dict[str, Any]:
    leaf_id = case["leaf_id"]
    case_dir = batch_dir / "cases" / leaf_id
    receipt_path = case_dir / "receipt.json"
    existing = validate_resumable_receipt(receipt_path, case, manifest_sha)
    if existing:
        return existing
    primary_id = case["dedup_primary_leaf_id"]
    if primary_id != leaf_id and primary_id in primary_receipts:
        primary = primary_receipts[primary_id]
        receipt = dict(primary)
        receipt.update(leaf_id=leaf_id, source_result_sha256=case["result_sha256"],
                       deduplicated_from_leaf_id=primary_id,
                       certification_basis="Byte-identical exact CNF and compressed/raw proof hashes.")
        atomic_create(receipt_path, receipt)
        return receipt
    result_path = ROOT / case["result_path"]
    if sha(result_path) != case["result_sha256"]:
        raise ValueError(f"source result hash mismatch: {leaf_id}")
    result = json.loads(result_path.read_text())
    parent, index = lookup[leaf_id]
    if result["fourth_parent_id"] != parent["id"] or result["fifth_index"] != index:
        raise ValueError(f"source identity mismatch: {leaf_id}")
    parent_path = ROOT / parent["third_level_parent_cnf"]["path"]
    if verified_parent_hashes.get(parent["id"]) != result["parent_cnf_sha256"]:
        raise ValueError(f"parent CNF binding mismatch: {leaf_id}")
    inherited = parent["inherited_fourth_units"]
    fifth = fifth_units(parent, index)
    if unit_sha(inherited) != result["inherited_fourth_unit_sha256"] or unit_sha(fifth) != result["fifth_unit_sha256"]:
        raise ValueError(f"unit recipe binding mismatch: {leaf_id}")
    proof_path = ROOT / result["proof"]["path"]
    if sha(proof_path) != result["proof"]["sha256"]:
        raise ValueError(f"compressed proof hash mismatch: {leaf_id}")
    case_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=f"cert-{leaf_id[-16:]}-") as temporary:
        temp = Path(temporary)
        cnf_path, raw_proof = temp / "instance.cnf", temp / "proof.drat"
        reconstruction_started = time.monotonic()
        variables, clauses = write_exact_cnf(parent_path, inherited + fifth, cnf_path)
        reconstruction_seconds = time.monotonic() - reconstruction_started
        cnf_hash = sha(cnf_path)
        if cnf_hash != result["exact_cnf_sha256"]:
            raise ValueError(f"exact CNF reconstruction mismatch: {leaf_id}")
        decompression_started = time.monotonic()
        with gzip.open(proof_path, "rb") as source, raw_proof.open("wb") as target:
            shutil.copyfileobj(source, target, length=1024 * 1024)
        decompression_seconds = time.monotonic() - decompression_started
        raw_hash = sha(raw_proof)
        if raw_hash != result["proof"]["uncompressed_sha256"]:
            raise ValueError(f"raw proof hash mismatch: {leaf_id}")
        replay_started = time.monotonic()
        checked = subprocess.run([str(CHECKER), str(cnf_path), str(raw_proof)], capture_output=True, text=True, timeout=600)
        replay_seconds = time.monotonic() - replay_started
        replay_log = (checked.stdout + checked.stderr).encode()
        if checked.returncode != 0 or b"VERIFIED" not in replay_log:
            raise ValueError(f"external replay failed: {leaf_id}")
        log_path = case_dir / "replay.log"
        if log_path.exists() and log_path.read_bytes() != replay_log:
            raise ValueError(f"immutable replay log disagreement: {leaf_id}")
        if not log_path.exists():
            log_path.write_bytes(replay_log)
        receipt = {
            "schema_version": 1, "status": "CERTIFIED_UNSAT", "leaf_id": leaf_id,
            "batch_manifest_sha256": manifest_sha, "source_result_sha256": case["result_sha256"],
            "exact_cnf_sha256": cnf_hash, "exact_cnf_variables": variables, "exact_cnf_clauses": clauses,
            "proof_sha256": result["proof"]["sha256"], "raw_proof_sha256": raw_hash,
            "checker_sha256": sha(CHECKER), "replay_exit_code": checked.returncode,
            "replay_log_sha256": sha(log_path),
            "timings_seconds": {"reconstruction": reconstruction_seconds, "decompression": decompression_seconds, "external_replay": replay_seconds},
            "certification_basis": "Fresh exact-CNF reconstruction, compressed/raw proof hash verification, and external drat-trim VERIFIED replay.",
        }
        atomic_create(receipt_path, receipt)
        return receipt


def update_certified_ledger() -> dict[str, Any]:
    sampled = sampled_certified_ids()
    receipts = sorted(CERT_BASE.glob("batches/batch-*/cases/*/receipt.json"))
    batch_ids = {path.parent.name for path in receipts if json.loads(path.read_text()).get("status") == "CERTIFIED_UNSAT"}
    overlap = sampled & batch_ids
    ledger = {
        "schema_version": 1, "status": "CURRENT",
        "route_manifest_sha256": sha(BASE / "suffix-scale-manifest.json"),
        "counts": {"sampled_operational_replay_certificates": len(sampled),
                   "exhaustive_batch_certificates": len(batch_ids),
                   "overlap": len(overlap), "distinct_certified_suffix_unsat": len(sampled | batch_ids)},
        "sampled_leaf_ids_sha256": hashlib.sha256(("\n".join(sorted(sampled)) + "\n").encode()).hexdigest(),
        "batch_leaf_ids_sha256": hashlib.sha256(("\n".join(sorted(batch_ids)) + "\n").encode()).hexdigest(),
        "complete_fourth_parents_closed": 0,
        "claim_limit": "This ledger certifies individual suffix leaves only. It does not close a fourth-level parent or complete the ordinary classification.",
    }
    target = CERT_BASE / "certified-ledger.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(".json.tmp")
    temporary.write_bytes(json_bytes(ledger))
    os.replace(temporary, target)
    return ledger


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch-id", type=int, required=True)
    parser.add_argument("--limit", type=int, default=1024)
    parser.add_argument("--parallelism", type=int, default=2)
    parser.add_argument("--plan-only", action="store_true")
    args = parser.parse_args()
    if args.limit < 1 or not 1 <= args.parallelism <= 8:
        raise ValueError("invalid batch limit or parallelism")
    manifest_path, manifest = make_manifest(args.batch_id, args.limit, args.parallelism)
    print(json.dumps({"manifest": str(manifest_path.relative_to(ROOT)), "sha256": sha(manifest_path),
                      "selected": len(manifest["cases"]), "plan_only": args.plan_only}, sort_keys=True))
    if args.plan_only:
        return
    _, lookup = load_domain()
    verified_parent_hashes = verify_parent_cache(manifest)
    batch_dir = manifest_path.parent
    manifest_sha = sha(manifest_path)
    started = time.monotonic()
    receipts: list[dict[str, Any]] = []
    # Primaries first makes byte-identical alias reuse deterministic.  In normal
    # campaign data almost every binding is unique, so replay remains parallel.
    primary_cases = [case for case in manifest["cases"] if case["dedup_primary_leaf_id"] == case["leaf_id"]]
    alias_cases = [case for case in manifest["cases"] if case["dedup_primary_leaf_id"] != case["leaf_id"]]
    primary_receipts: dict[str, dict[str, Any]] = {}
    with ThreadPoolExecutor(max_workers=manifest["parallelism"]) as pool:
        futures = {pool.submit(certify_one, case, lookup, batch_dir, manifest_sha, {}, verified_parent_hashes): case for case in primary_cases}
        for future in as_completed(futures):
            receipt = future.result()
            primary_receipts[receipt["leaf_id"]] = receipt
            receipts.append(receipt)
    for case in alias_cases:
        receipt = certify_one(case, lookup, batch_dir, manifest_sha, primary_receipts, verified_parent_hashes)
        receipts.append(receipt)
    receipts.sort(key=lambda row: row["leaf_id"])
    batch_receipt = {
        "schema_version": 1, "status": "COMPLETE", "batch_id": args.batch_id,
        "batch_manifest_sha256": manifest_sha, "selected": len(manifest["cases"]),
        "certified_unsat": len(receipts), "deduplicated_replays": len(alias_cases),
        "wall_seconds": time.monotonic() - started,
        "case_receipt_set_sha256": hashlib.sha256(("\n".join(
            f"{row['leaf_id']} {sha(batch_dir / 'cases' / row['leaf_id'] / 'receipt.json')}" for row in receipts) + "\n").encode()).hexdigest(),
        "claim_limit": "Individual suffix leaves certified; no fourth-level parent aggregation is asserted.",
    }
    atomic_create(batch_dir / "batch-receipt.json", batch_receipt)
    ledger = update_certified_ledger()
    print(json.dumps({"batch_receipt": batch_receipt, "certified_ledger_counts": ledger["counts"]}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Independent exact-CNF reconstruction and replay for one suffix segment."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import itertools
import json
import os
import statistics
import subprocess
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from pysat.formula import CNF

from verify_ordinary_c1153_classification import normalized_orbit_bfs, read_cover


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "artifacts/classification/ordinary-c1153-v1/hard-tail-fifth-split"
CHECKER = ROOT / ".venv/sat-audit-tools/drat-trim/drat-trim"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def unit_sha(units: list[int]) -> str:
    return hashlib.sha256((" ".join(map(str, units)) + "\n").encode()).hexdigest()


def units_for(parent: dict[str, object], index: int) -> list[int]:
    earlier = [value for orbit in parent["fifth_orbits"][:index] for value in orbit["member_variables"]]
    return [-value for value in earlier] + [parent["fifth_orbits"][index]["canonical_variable"]]


def audit_one(parent: dict[str, object], index: int, leaf_id: str, result: dict[str, object], representative: tuple[tuple[int, ...], ...]) -> dict[str, object]:
    if result["leaf_id"] != leaf_id or result["fifth_index"] != index or result["fourth_parent_id"] != parent["id"]:
        raise ValueError(f"{leaf_id}: result identity mismatch")
    parent_path = ROOT / parent["third_level_parent_cnf"]["path"]
    if sha(parent_path) != parent["third_level_parent_cnf"]["sha256"]:
        raise ValueError(f"{leaf_id}: parent CNF hash mismatch")
    fifth = units_for(parent, index)
    if unit_sha(fifth) != result["fifth_unit_sha256"]:
        raise ValueError(f"{leaf_id}: fifth unit recipe mismatch")
    solver_log = ROOT / result["solver_log"]["path"]
    if sha(solver_log) != result["solver_log"]["sha256"]:
        raise ValueError(f"{leaf_id}: solver log hash mismatch")
    if result["status"] == "FIXED_CAP_TIMEOUT":
        if "UNKNOWN" not in solver_log.read_text():
            raise ValueError(f"{leaf_id}: timeout lacks UNKNOWN status")
        return {"leaf_id": leaf_id, "parent_id": parent["id"], "position": result["position"], "status": "FIXED_CAP_TIMEOUT"}
    if result["status"] == "SAT_VALID_COVER_PENDING_ISOMORPHISM_AUDIT":
        witness_path = ROOT / result["witness"]["path"]
        if sha(witness_path) != result["witness"]["sha256"]:
            raise ValueError(f"{leaf_id}: witness hash mismatch")
        witness = read_cover(witness_path)
        isomorphic = any(witness in normalized_orbit_bfs(normalize_seed) for normalize_seed in (representative,))
        return {"leaf_id": leaf_id, "parent_id": parent["id"], "position": result["position"], "status": "SAT_VALIDATED",
                "isomorphic_to_maintained_cover": isomorphic, "witness_sha256": result["witness"]["sha256"]}
    if result["status"] not in ("UNSAT_VERIFIED_BY_RUNNER", "PROVISIONAL_UNSAT_PROOF_RETAINED"):
        raise ValueError(f"{leaf_id}: unsupported result status {result['status']}")
    proof_path = ROOT / result["proof"]["path"]
    if sha(proof_path) != result["proof"]["sha256"]:
        raise ValueError(f"{leaf_id}: compressed proof hash mismatch")
    with tempfile.TemporaryDirectory(prefix="ordinary-fifth-suffix-audit-") as temporary:
        temp = Path(temporary)
        cnf_path, raw_proof, recompressed = temp / "instance.cnf", temp / "proof.drat", temp / "proof.recompressed.drat.gz"
        reconstruction_started = time.monotonic()
        base = CNF(from_file=str(parent_path))
        exact = CNF(from_clauses=base.clauses + [[value] for value in parent["inherited_fourth_units"] + fifth])
        exact.to_file(str(cnf_path))
        exact_cnf_bytes = cnf_path.stat().st_size
        reconstruction_seconds = time.monotonic() - reconstruction_started
        if sha(cnf_path) != result["exact_cnf_sha256"]:
            raise ValueError(f"{leaf_id}: reconstructed exact CNF mismatch")
        with gzip.open(proof_path, "rb") as source, raw_proof.open("wb") as target:
            while chunk := source.read(1024 * 1024):
                target.write(chunk)
        if sha(raw_proof) != result["proof"]["uncompressed_sha256"]:
            raise ValueError(f"{leaf_id}: uncompressed proof hash mismatch")
        replay_started = time.monotonic()
        checked = subprocess.run([str(CHECKER), str(cnf_path), str(raw_proof)], capture_output=True, text=True, timeout=600)
        replay_seconds = time.monotonic() - replay_started
        if checked.returncode != 0 or "VERIFIED" not in checked.stdout + checked.stderr:
            raise ValueError(f"{leaf_id}: independent external replay failed")
        compression_started = time.monotonic()
        with raw_proof.open("rb") as source, recompressed.open("wb") as raw:
            with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0, compresslevel=6) as target:
                while chunk := source.read(1024 * 1024):
                    target.write(chunk)
        compression_seconds = time.monotonic() - compression_started
        if sha(recompressed) != result["proof"]["sha256"]:
            raise ValueError(f"{leaf_id}: deterministic recompression is not byte-identical")
    return {"leaf_id": leaf_id, "parent_id": parent["id"], "position": result["position"], "status": "UNSAT_REPLAYED",
            "proof_sha256": result["proof"]["sha256"], "compressed_bytes": result["proof"]["compressed_bytes"],
            "uncompressed_bytes": result["proof"]["uncompressed_bytes"], "exact_cnf_bytes": exact_cnf_bytes,
            "reconstruction_seconds": reconstruction_seconds, "replay_seconds": replay_seconds,
            "compression_benchmark_seconds": compression_seconds, "solver_seconds": result["solver_elapsed_seconds"]}


def distribution(values: list[float | int]) -> dict[str, float | int | None]:
    if not values:
        return {"count": 0, "min": None, "p25": None, "median": None, "p75": None, "p95": None, "max": None, "mean": None}
    ordered = sorted(values)
    pick = lambda fraction: ordered[round(fraction * (len(ordered) - 1))]
    return {"count": len(ordered), "min": ordered[0], "p25": pick(.25), "median": statistics.median(ordered),
            "p75": pick(.75), "p95": pick(.95), "max": ordered[-1], "mean": statistics.fmean(ordered)}


def free_bytes() -> int:
    stat = os.statvfs(ROOT)
    return stat.f_bavail * stat.f_frsize


def stratified_sample(leaf_ids: list[str], results: dict[str, dict[str, object]], size: int, seed: str) -> list[str]:
    groups = {label: [] for label in ("first_quartile", "middle_quartile", "last_quartile")}
    for leaf_id in leaf_ids:
        groups[results[leaf_id]["position"]].append(leaf_id)
    exact = {label: size * len(rows) / len(leaf_ids) for label, rows in groups.items()}
    allocation = {label: int(value) for label, value in exact.items()}
    for label in sorted(groups, key=lambda key: (exact[key] - allocation[key], key), reverse=True)[:size - sum(allocation.values())]:
        allocation[label] += 1
    chosen = []
    for label, rows in groups.items():
        ranked = sorted(rows, key=lambda leaf_id: hashlib.sha256(f"{seed}:{leaf_id}".encode()).hexdigest())
        chosen.extend(ranked[:allocation[label]])
    return sorted(chosen, key=leaf_ids.index)


def operational_sample(leaf_ids: list[str], results: dict[str, dict[str, object]], lookup: dict[str, tuple[dict[str, object], int]], size: int, seed: str) -> list[str]:
    rank = lambda leaf_id: hashlib.sha256(f"{seed}:{leaf_id}".encode()).hexdigest()
    chosen: set[str] = {leaf_id for leaf_id in leaf_ids if results[leaf_id]["status"] != "PROVISIONAL_UNSAT_PROOF_RETAINED"}
    strata: dict[tuple[str, str, str], list[str]] = {}
    for leaf_id in leaf_ids:
        parent, _ = lookup[leaf_id]
        key = (parent["prior_status"], parent["top_parent"], results[leaf_id]["position"])
        strata.setdefault(key, []).append(leaf_id)
    for rows in strata.values():
        chosen.add(min(rows, key=rank))
    by_size = sorted((leaf_id for leaf_id in leaf_ids if "proof" in results[leaf_id]),
                     key=lambda leaf_id: (results[leaf_id]["proof"]["compressed_bytes"], leaf_id))
    for fraction in (0, .25, .5, .75, .95, 1):
        chosen.add(by_size[round(fraction * (len(by_size) - 1))])
    chosen.update(by_size[-8:])
    for leaf_id in sorted(leaf_ids, key=rank):
        if len(chosen) >= size:
            break
        chosen.add(leaf_id)
    if len(chosen) > size:
        protected = set(by_size[-8:]) | {by_size[round(f * (len(by_size) - 1))] for f in (0, .25, .5, .75, .95, 1)}
        protected.update(leaf_id for leaf_id in chosen if results[leaf_id]["status"] != "PROVISIONAL_UNSAT_PROOF_RETAINED")
        removable = sorted(chosen - protected, key=rank, reverse=True)
        while len(chosen) > size and removable:
            chosen.remove(removable.pop(0))
    if len(chosen) != size:
        raise ValueError("operational sample could not meet its exact size")
    return sorted(chosen, key=leaf_ids.index)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--segment", type=int, default=0)
    parser.add_argument("--sample-size", type=int)
    args = parser.parse_args()
    route_path = BASE / "suffix-scale-manifest.json"
    route = json.loads(route_path.read_text())
    selection_audit_path = BASE / "suffix-scale-independent-audit.json"
    selection_audit = json.loads(selection_audit_path.read_text())
    if selection_audit["status"] != "VALID" or selection_audit["route_manifest_sha256"] != sha(route_path):
        raise ValueError("selection audit binding failed")
    segment_dir = BASE / "segments" / f"segment-{args.segment:04d}"
    manifest_path, receipt_path = segment_dir / "manifest.json", segment_dir / "runner-receipt.json"
    manifest, receipt = json.loads(manifest_path.read_text()), json.loads(receipt_path.read_text())
    if manifest["route_manifest"]["sha256"] != sha(route_path) or receipt["segment_manifest"]["sha256"] != sha(manifest_path):
        raise ValueError("route/segment/receipt binding failed")
    if receipt["status"] not in ("COMPLETE_PENDING_INDEPENDENT_AUDIT", "STOPPED_FOR_SAT"):
        raise ValueError("runner segment is not at an auditable stop")
    fifth_path = ROOT / route["fifth_manifest"]["path"]
    fifth = json.loads(fifth_path.read_text())
    parent_by_id = {row["id"]: row for row in fifth["parents"]}
    lookup = {f"{parent['id']}-fifth-{index:03d}": (parent, index)
              for parent in fifth["parents"] for index in range(parent["branch_count"])}
    leaf_ids = manifest["leaf_ids"]
    result_paths = sorted(segment_dir.glob("*/result.json"))
    results = {json.loads(path.read_text())["leaf_id"]: json.loads(path.read_text()) for path in result_paths}
    expected = set(leaf_ids[:receipt["completed"]])
    if set(results) != expected or len(results) != len(result_paths):
        raise ValueError("segment results are omitted, duplicated, or outside the completed prefix")
    audit_leaf_ids = leaf_ids[:receipt["completed"]]
    if args.sample_size is not None:
        if not 1 <= args.sample_size <= len(audit_leaf_ids):
            raise ValueError("invalid independent sample size")
        audit_leaf_ids = (stratified_sample(audit_leaf_ids, results, args.sample_size, sha(manifest_path)) if args.segment == 0
                          else operational_sample(audit_leaf_ids, results, lookup, args.sample_size, sha(manifest_path)))
    class_manifest = json.loads((ROOT / "artifacts/classification/ordinary-c1153-v1/manifest.json").read_text())
    representative = read_cover(ROOT / class_manifest["known_class_blocking"]["representative"]["path"])
    rows = []
    audit_started = time.monotonic()
    free_at_audit_start = free_bytes()
    minimum_free = [free_at_audit_start]
    monitor_stop = threading.Event()

    def monitor_disk() -> None:
        while not monitor_stop.wait(0.05):
            minimum_free[0] = min(minimum_free[0], free_bytes())

    monitor = threading.Thread(target=monitor_disk, daemon=True)
    monitor.start()
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = []
        for leaf_id in audit_leaf_ids:
            parent, index = lookup[leaf_id]
            futures.append(pool.submit(audit_one, parent, index, leaf_id, results[leaf_id], representative))
        for future in as_completed(futures):
            rows.append(future.result())
    monitor_stop.set()
    monitor.join()
    audit_wall_seconds = time.monotonic() - audit_started
    rows.sort(key=lambda row: leaf_ids.index(row["leaf_id"]))
    labels = ("first_quartile", "middle_quartile", "last_quartile")
    by_position = {label: {status: sum(row["position"] == label and row["status"] == status for row in rows)
                           for status in ("UNSAT_REPLAYED", "FIXED_CAP_TIMEOUT", "SAT_VALIDATED")} for label in labels}
    replayed = [row for row in rows if row["status"] == "UNSAT_REPLAYED"]
    sat = [row for row in rows if row["status"] == "SAT_VALIDATED"]
    all_runner_unsat = [results[leaf_id] for leaf_id in leaf_ids[:receipt["completed"]]
                        if results[leaf_id]["status"] in ("UNSAT_VERIFIED_BY_RUNNER", "PROVISIONAL_UNSAT_PROOF_RETAINED")]
    proof_bytes = sum(row["proof"]["compressed_bytes"] for row in all_runner_unsat)
    closure_rate = len(all_runner_unsat) / receipt["completed"] if receipt["completed"] else 0.0
    mean_bytes = proof_bytes / len(all_runner_unsat) if all_runner_unsat else None
    projected_full_bytes = round((mean_bytes or 0) * route["accounting"]["pending_scale_workload"])
    solver_distribution = distribution([row["solver_elapsed_seconds"] for row in all_runner_unsat])
    reconstruction_distribution = distribution([row["reconstruction_seconds"] for row in replayed])
    compression_distribution = distribution([row["compression_benchmark_seconds"] for row in replayed])
    replay_distribution = distribution([row["replay_seconds"] for row in replayed])
    compressed_size_distribution = distribution([row["proof"]["compressed_bytes"] for row in all_runner_unsat])
    raw_size_distribution = distribution([row["proof"]["uncompressed_bytes"] for row in all_runner_unsat])
    pending = route["accounting"]["pending_scale_workload"]
    projected_production_host_hours = receipt["wall_seconds"] / receipt["completed"] * pending / 3600
    projected_sampled_audit_host_hours = audit_wall_seconds / receipt["completed"] * pending / 3600
    projected_exhaustive_second_audit_host_hours = audit_wall_seconds / len(rows) * pending / 3600
    projected_solver_cpu_hours = solver_distribution["mean"] * pending / 3600
    persistent_segment_bytes = sum(path.stat().st_size for path in segment_dir.rglob("*") if path.is_file())
    four_largest_raw = sum(sorted((row["proof"]["uncompressed_bytes"] for row in all_runner_unsat), reverse=True)[:4])
    four_largest_cnf = sum(sorted((row["exact_cnf_bytes"] for row in replayed), reverse=True)[:4])
    conservative_runner_peak_bytes = persistent_segment_bytes + four_largest_raw + four_largest_cnf
    # Parent closure requires all children terminal. Timeouts and unmeasured leaves remain open.
    known_terminal = set(route["excluded_measured_leaf_ids"]) | {row["leaf_id"] for row in replayed} | {row["leaf_id"] for row in sat}
    complete_parents = []
    for parent in fifth["parents"]:
        children = {f"{parent['id']}-fifth-{index:03d}" for index in range(parent["branch_count"])}
        if children <= known_terminal:
            complete_parents.append(parent["id"])
    sampled_unsat_expected = sum(results[leaf_id]["status"] in ("UNSAT_VERIFIED_BY_RUNNER", "PROVISIONAL_UNSAT_PROOF_RETAINED") for leaf_id in audit_leaf_ids)
    replay_success = len(replayed) == sampled_unsat_expected
    gate = (not sat and replay_success and closure_rate >= 39 / 48 and (mean_bytes or 0) <= 1024 * 1024
            and proof_bytes <= manifest["artifact_budget"]["compressed_proof_bytes"]
            and projected_full_bytes <= route["storage_plan"]["storage_limit_bytes"])
    cumulative_completed = 0
    for number in range(args.segment + 1):
        prior_receipt = BASE / "segments" / f"segment-{number:04d}" / "runner-receipt.json"
        if prior_receipt.exists():
            cumulative_completed += json.loads(prior_receipt.read_text())["completed"]
    report = {
        "schema_version": 1, "status": "VALID", "segment": args.segment,
        "route_manifest_sha256": sha(route_path), "segment_manifest_sha256": sha(manifest_path),
        "runner_receipt_sha256": sha(receipt_path), "checker_sha256": sha(CHECKER),
        "selected": len(leaf_ids), "completed": receipt["completed"], "independent_sample_size": len(audit_leaf_ids),
        "independent_sample_rule": ("Position-stratified deterministic SHA-256 ranking bound to the immutable segment manifest." if args.segment == 0
                                    else "Deterministic QA covering parent-type x position strata, proof-size quantiles, eight largest proofs, and SHA-256 fill, bound to the immutable segment manifest."),
        "independent_sample_leaf_ids": audit_leaf_ids,
        "ledgers": {"provisional_harvest": {"solver_unsat_with_retained_proof": len(all_runner_unsat)},
                    "certified": {"independently_reconstructed_and_replayed": len(replayed)}},
        "counts": {"RUNNER_OR_PROVISIONAL_UNSAT_WITH_PROOF": len(all_runner_unsat), "INDEPENDENT_SAMPLE_UNSAT_REPLAYED": len(replayed), "FIXED_CAP_TIMEOUT": sum(row["status"] == "FIXED_CAP_TIMEOUT" for row in results.values()), "SAT_VALIDATED": len(sat)},
        "counts_by_position": by_position, "replay_success_rate": 1.0 if replay_success else 0.0,
        "closure_rate": closure_rate, "compressed_proof_bytes": proof_bytes, "mean_compressed_proof_bytes": mean_bytes,
        "timings_seconds": {"segment_runner_wall": receipt["wall_seconds"], "independent_audit_wall": audit_wall_seconds,
                            "solver_per_case": solver_distribution, "cnf_reconstruction_per_case": reconstruction_distribution,
                            "compression_benchmark_per_case": compression_distribution, "independent_replay_per_case": replay_distribution},
        "proof_size_bytes": {"compressed": compressed_size_distribution, "uncompressed": raw_size_distribution},
        "disk": {"persistent_segment_bytes": persistent_segment_bytes,
                 "audit_observed_peak_additional_bytes_from_free_space_sampling": max(0, free_at_audit_start - minimum_free[0]),
                 "runner_peak_conservative_bound_bytes": conservative_runner_peak_bytes,
                 "runner_peak_bound_method": "Final persistent segment plus the four largest raw proofs and four largest exact CNFs; runner telemetry was not changed mid-segment."},
        "projected_full_pending_proof_bytes_at_observed_mean": projected_full_bytes,
        "projection_comparison": {"predeclared_proof_bytes": route["storage_plan"]["projected_pending_proof_bytes"],
                                  "observed_mean_projected_proof_bytes": projected_full_bytes,
                                  "projected_production_pipeline_host_hours": projected_production_host_hours,
                                  "projected_solver_cpu_hours": projected_solver_cpu_hours,
                                  "projected_sampled_second_audit_host_hours": projected_sampled_audit_host_hours,
                                  "projected_exhaustive_second_audit_host_hours": projected_exhaustive_second_audit_host_hours,
                                  "projected_production_plus_sampled_audit_host_hours": projected_production_host_hours + projected_sampled_audit_host_hours},
        "remaining_route_branches": route["accounting"]["pending_scale_workload"] - cumulative_completed,
        "complete_fourth_parents_closed": len(complete_parents), "complete_fourth_parent_ids": complete_parents,
        "continuation_gate_passed": gate,
        "continuation_gate_numeric": "100% independent replay of deterministic sample; >=39/48 runner closure; <=1 MiB mean proof; <=64 MiB segment; <=6 GiB projected total; no SAT.",
        "results": rows,
        "claim_limit": ("Segment 0 runner UNSATs have exact-CNF drat-trim replay; its deterministic subset has an independent second replay. " if args.segment == 0 else
                        "Solver UNSATs outside the deterministic QA sample remain provisional. ")
                       + "Final classification requires exhaustive aggregate replay before parent closure.",
    }
    target = segment_dir / "independent-audit.json"
    target.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({key: report[key] for key in ("status", "selected", "completed", "counts", "counts_by_position", "replay_success_rate", "closure_rate", "compressed_proof_bytes", "mean_compressed_proof_bytes", "timings_seconds", "proof_size_bytes", "disk", "projected_full_pending_proof_bytes_at_observed_mean", "projection_comparison", "remaining_route_branches", "complete_fourth_parents_closed", "continuation_gate_passed", "claim_limit")}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

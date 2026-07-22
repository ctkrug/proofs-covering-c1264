#!/usr/bin/env python3
"""Ingest a completed fixed-benchmark tranche into the single portfolio manifest."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.build_certificate_portfolio import ROOT, canonical_hash  # noqa: E402


MANIFEST = ROOT / "artifacts/portfolio/frontier-manifest-v1.json"
RUN_ROOT = Path("artifacts/cardinality-encoding-benchmark/cardinality-encoding-20-leaf-20260722")
CHECKPOINT = RUN_ROOT / "checkpoint.json"
RUN_ID = "cardinality-encoding-20-leaf-20260722"
TRANCHE_ID = f"{RUN_ID}-final"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def receipt(path: Path) -> dict[str, str]:
    return {"path": str(path), "sha256": sha(ROOT / path)}


def ingest() -> dict:
    manifest = json.loads(MANIFEST.read_text())
    checkpoint = json.loads((ROOT / CHECKPOINT).read_text())
    if len(checkpoint.get("results", [])) != 40 or len(checkpoint.get("completed", [])) != 40:
        raise ValueError("the frozen 20-leaf/2-method benchmark is not complete")
    monotonicity = manifest.get("blocker_monotonicity", {})
    if monotonicity.get("status") != "strict_superset_verified":
        raise ValueError("active five-orbit blocker has not passed monotonic-transfer audit")
    nodes = {row["id"]: row for row in manifest["nodes"]}
    for node in nodes.values():
        node["outcomes"] = [row for row in node["outcomes"] if row.get("run_id") != RUN_ID]
        certified = any(row.get("status") == "unsat_certified" for row in node["outcomes"])
        witnessed = any(row.get("status") == "sat_validated" for row in node["outcomes"])
        node["final_coverage_status"] = "closed_unsat" if certified else "closed_sat" if witnessed else "open"
    total_cpu = 0.0
    proof_bytes = 0
    method_stats = {name: {"tested": 0, "certified_unsat": 0, "net_new_closures": 0,
                           "cpu_seconds": 0.0, "proof_bytes": 0}
                    for name in ("sequential", "kmtotalizer")}
    newly_closed = []

    for result in checkpoint["results"]:
        node = nodes[result["leaf_id"]]
        method = result["encoding"]
        if method not in node["assigned_methods"]:
            node["assigned_methods"].append(method)
        folder = RUN_ROOT / result["leaf_id"] / method
        result_path = folder / "result.json"
        audit_path = folder / "cnf-audit.json"
        runtime = float(result["solver_elapsed_seconds"])
        total_cpu += runtime
        method_stats[method]["tested"] += 1
        method_stats[method]["cpu_seconds"] += runtime
        outcome = {
            "run_id": RUN_ID,
            "method": method,
            "status": "unknown",
            "runtime_seconds": runtime,
            "cpu_seconds": runtime,
            "cnf_encoding_revision": f"{RUN_ID}:{method}:schema-1",
            "cnf_sha256": result["cnf_sha256"],
            "result_receipt": receipt(result_path),
            "independent_audit_receipt": receipt(audit_path),
        }
        audit = json.loads((ROOT / audit_path).read_text())
        if audit.get("status") != "valid" or audit.get("cnf_sha256") != result["cnf_sha256"]:
            raise ValueError(f"semantic audit disagreement for {result['leaf_id']} {method}")
        if result["status"] == "UNSAT_VERIFIED":
            validation_path = folder / "validation.json"
            validation = json.loads((ROOT / validation_path).read_text())
            proof = result.get("proof") or {}
            if validation.get("status") != "verified" or validation.get("proof", {}).get("sha256") != proof.get("sha256"):
                raise ValueError(f"proof replay disagreement for {result['leaf_id']} {method}")
            outcome.update({
                "status": "unsat_certified",
                "proof_sha256": proof["sha256"],
                "proof_bytes": int(proof["bytes"]),
                "replay_receipt": receipt(validation_path),
            })
            method_stats[method]["certified_unsat"] += 1
            method_stats[method]["proof_bytes"] += int(proof["bytes"])
            proof_bytes += int(proof["bytes"])
        node["outcomes"] = [row for row in node["outcomes"]
                            if not (row.get("run_id") == RUN_ID and row.get("method") == method)]
        node["outcomes"].append(outcome)
        node["outcomes"].sort(key=lambda row: (row.get("run_id", ""), row.get("method", "")))

    # Attribute a net-new closure to the first certified method in the fixed execution order.
    method_order = {"sequential": 0, "kmtotalizer": 1}
    for node in manifest["nodes"]:
        certified = sorted((row for row in node["outcomes"] if row.get("status") == "unsat_certified"),
                           key=lambda row: method_order.get(row["method"], 99))
        was_closed = node["final_coverage_status"] != "open"
        if certified:
            node["final_coverage_status"] = "closed_unsat"
            if not was_closed:
                newly_closed.append(node["id"])
                method_stats[certified[0]["method"]]["net_new_closures"] += 1

    closed = sum(row["final_coverage_status"] != "open" for row in manifest["nodes"])
    manifest["counts"] = {"total": 47, "closed": closed, "open": 47 - closed}
    remaining = [row for row in manifest["nodes"] if row["final_coverage_status"] == "open"]
    for stats in method_stats.values():
        stats["cpu_seconds"] = round(stats["cpu_seconds"], 6)
        stats["net_new_closures_per_cpu_hour"] = round(
            stats["net_new_closures"] / (stats["cpu_seconds"] / 3600), 6
        ) if stats["net_new_closures"] else 0.0
    source_results = []
    for result in checkpoint["results"]:
        result_path = RUN_ROOT / result["leaf_id"] / result["encoding"] / "result.json"
        source_results.append(receipt(result_path))
    tranche = {
        "id": TRANCHE_ID,
        "source_results": sorted(source_results, key=lambda row: row["path"]),
        "superseded_mutable_checkpoint": {
            "path": str(CHECKPOINT),
            "final_sha256": sha(ROOT / CHECKPOINT),
            "reason": "checkpoint advanced in place during the frozen benchmark; immutable result receipts are authoritative",
        },
        "blocker_transfer": {
            "status": monotonicity["status"],
            "predecessor_blocker": manifest["predecessor_link_blocker"],
            "active_blocker": manifest["active_link_blocker"],
            "added_clauses": monotonicity["added_clauses"],
            "consequence": "UNSAT under the predecessor blocker remains UNSAT under the active stronger blocker",
        },
        "completed_solver_runs": len(checkpoint["results"]),
        "newly_closed_nodes": sorted(newly_closed),
        "cumulative_closed_out_of_47": f"{closed}/47",
        "remaining_node_classes": {
            "secondary": sum(row["kind"] == "secondary" for row in remaining),
            "tertiary": sum(row["kind"] == "tertiary" for row in remaining),
        },
        "certificate_and_replay_status": {
            "certified_unsat_outcomes": sum(x["certified_unsat"] for x in method_stats.values()),
            "distinct_certified_nodes": closed,
            "semantic_audits": "all ingested outcomes valid",
            "proof_replays": "all certified UNSAT outcomes verified"
        },
        "cpu_seconds": round(total_cpu, 6),
        "proof_storage_bytes": proof_bytes,
        "cost_per_new_closure": {
            "cpu_seconds": round(total_cpu / len(newly_closed), 6) if newly_closed else None,
            "proof_bytes": round(proof_bytes / len(newly_closed), 6) if newly_closed else None,
        },
        "method_stats": method_stats,
        "next_method_by_hard_tail_class": {
            "fixed_benchmark_sample": "complete; do not expand kmtotalizer because it earned zero unique closures",
            "unclosed_secondary": "sequential default, with structural/constructive exceptions assigned by the dynamic plan",
            "unclosed_tertiary": "sequential default, with structural/constructive exceptions assigned by the dynamic plan",
            "constructive_global_uncertainty": "forced-matching exact-degree 40-block witness search remains active"
        }
    }
    manifest["tranches"] = [
        row for row in manifest["tranches"]
        if row.get("id") not in {tranche["id"], f"{RUN_ID}-segment-01"}
    ] + [tranche]
    manifest.pop("manifest_payload_sha256", None)
    manifest["manifest_payload_sha256"] = canonical_hash(manifest)
    return manifest


def main() -> None:
    value = ingest()
    MANIFEST.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    print(f"updated {MANIFEST}: {value['counts']['closed']}/47 closed")


if __name__ == "__main__":
    main()

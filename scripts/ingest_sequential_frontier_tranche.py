#!/usr/bin/env python3
"""Ingest one immutable sequential tranche without overstating SAT link witnesses."""

from __future__ import annotations

import hashlib
import json
import argparse
from pathlib import Path

from build_certificate_portfolio import canonical_hash


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "artifacts/portfolio/frontier-manifest-v1.json"
CHECKPOINT = Path("artifacts/sequential-frontier-sweep/sequential-open-frontier-30-v5-native-replay-20260722/checkpoint.json")
RUN_ID = "sequential-open-frontier-30-v5-native-replay-20260722"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def receipt(path: Path) -> dict[str, str]:
    return {"path": str(path), "sha256": sha(ROOT / path)}


def ingest(checkpoint_path: Path = CHECKPOINT, run_id: str = RUN_ID,
           tranche_audit_path: Path | None = None) -> dict:
    manifest = json.loads(MANIFEST.read_text())
    checkpoint = json.loads((ROOT / checkpoint_path).read_text())
    tranche_audit = None
    audited = {}
    if tranche_audit_path is not None:
        tranche_audit = json.loads((ROOT / tranche_audit_path).read_text())
        if tranche_audit.get("status") != "valid":
            raise ValueError("frozen-tranche independent audit is not valid")
        if tranche_audit["checkpoint"]["sha256"] != sha(ROOT / checkpoint_path):
            raise ValueError("frozen-tranche independent audit is bound to another checkpoint")
        audited = {row["leaf_id"]: row for row in tranche_audit["results"]}
    nodes = {row["id"]: row for row in manifest["nodes"]}
    before = {row["id"] for row in manifest["nodes"] if row["final_coverage_status"] != "open"}
    sources = []
    cpu = 0.0
    proof_bytes = 0
    certified = []
    for result in checkpoint["results"]:
        node = nodes[result["leaf_id"]]
        if node["final_coverage_status"] != "open" and not any(
            row.get("run_id") == run_id for row in node["outcomes"]
        ):
            raise ValueError(f"refusing to rerun transferred closure {node['id']}")
        if "sequential" not in node["assigned_methods"]:
            node["assigned_methods"].append("sequential")
        folder = Path(result["path"])
        result_path = folder / "result.json"
        audit_path = folder / "cnf-audit.json"
        audit = json.loads((ROOT / audit_path).read_text())
        if audit.get("status") != "valid" or audit.get("cnf_sha256") != result["cnf_sha256"]:
            raise ValueError(f"CNF audit disagreement for {node['id']}")
        runtime = float(result["solver_elapsed_seconds"])
        cpu += runtime
        outcome = {
            "run_id": run_id,
            "method": "sequential",
            "status": "unknown",
            "runtime_seconds": runtime,
            "cpu_seconds": runtime,
            "cnf_encoding_revision": f"{run_id}:sequential:schema-2",
            "cnf_sha256": result["cnf_sha256"],
            "result_receipt": receipt(result_path),
            "independent_audit_receipt": receipt(audit_path),
        }
        if result["status"] == "UNSAT_VERIFIED":
            validation_path = folder / "validation.json"
            validation = json.loads((ROOT / validation_path).read_text())
            proof = result["proof"]
            if validation.get("status") != "verified" or validation["proof"]["sha256"] != proof["sha256"]:
                raise ValueError(f"proof replay disagreement for {node['id']}")
            if tranche_audit is None:
                raise ValueError("refusing to ingest UNSAT without a post-tranche independent audit")
            independent = audited.get(node["id"])
            if not independent or independent.get("independent_replay") != "verified":
                raise ValueError(f"post-tranche independent replay missing for {node['id']}")
            if independent.get("proof_sha256") != proof["sha256"]:
                raise ValueError(f"post-tranche proof hash disagreement for {node['id']}")
            outcome.update({
                "status": "unsat_certified",
                "proof_sha256": proof["sha256"],
                "proof_bytes": int(proof["bytes"]),
                "replay_receipt": receipt(validation_path),
                "post_tranche_independent_replay_receipt": receipt(tranche_audit_path),
            })
            proof_bytes += int(proof["bytes"])
            certified.append(node["id"])
            node["final_coverage_status"] = "closed_unsat"
        elif result["status"] == "SAT_NEW_ORBIT":
            validation_path = folder / "validation.json"
            witness_path = folder / "witness.txt"
            validation = json.loads((ROOT / validation_path).read_text())
            if validation.get("status") != "valid-new-link-orbit":
                raise ValueError(f"link witness validation disagreement for {node['id']}")
            if validation.get("witness_sha256") != sha(ROOT / witness_path):
                raise ValueError(f"link witness hash disagreement for {node['id']}")
            outcome.update({
                "status": "provisional_sat",
                "local_claim": "validated exact-degree C(11,5,3) link outside the active catalogue; not a 40-cover",
                "link_witness_receipt": receipt(witness_path),
                "link_validation_receipt": receipt(validation_path),
                "canonical_link_sha256": validation["canonical_sha256"],
            })
        node["outcomes"] = [row for row in node["outcomes"] if row.get("run_id") != run_id]
        node["outcomes"].append(outcome)
        node["outcomes"].sort(key=lambda row: (row.get("run_id", ""), row.get("method", "")))
        sources.append(receipt(result_path))
    newly_closed = sorted(set(certified) - before)
    closed = sum(row["final_coverage_status"] != "open" for row in manifest["nodes"])
    manifest["counts"] = {"total": 47, "closed": closed, "open": 47 - closed}
    remaining = [row for row in manifest["nodes"] if row["final_coverage_status"] == "open"]
    tranche = {
        "id": f"{run_id}-segment-01",
        "source_results": sorted(sources, key=lambda row: row["path"]),
        "completed_solver_runs": len(checkpoint["results"]),
        "newly_closed_nodes": newly_closed,
        "cumulative_closed_out_of_47": f"{closed}/47",
        "remaining_node_classes": {
            "secondary": sum(row["kind"] == "secondary" for row in remaining),
            "tertiary": sum(row["kind"] == "tertiary" for row in remaining),
        },
        "certificate_and_replay_status": {
            "certified_unsat_outcomes": len(certified),
            "semantic_audits": f"all {len(checkpoint['results'])} outcomes passed their declared semantic gate",
            "proof_replays": f"all {len(certified)} UNSAT outcomes independently verified",
        },
        "cpu_seconds": round(cpu, 6),
        "proof_storage_bytes": proof_bytes,
        "cost_per_new_closure": {
            "cpu_seconds": round(cpu / len(newly_closed), 6),
            "proof_bytes": round(proof_bytes / len(newly_closed), 6),
        },
        "method_stats": {
            "sequential": {
                "tested": len(checkpoint["results"]),
                "certified_unsat": len(certified),
                "net_new_closures": len(newly_closed),
                "cpu_seconds": round(cpu, 6),
                "proof_bytes": proof_bytes,
                "net_new_closures_per_cpu_hour": round(len(newly_closed) / (cpu / 3600), 6),
            }
        },
        "next_method_by_hard_tail_class": {
            "unmeasured_open": "continue ordered sequential harvest at the same fixed cap",
            "sequential_timeout": "classify structurally before any longer or alternative run",
            "fifth_orbit_tree_case": "structural lemma/branch analysis; do not blindly raise timeout",
        },
    }
    manifest["tranches"] = [row for row in manifest["tranches"] if row.get("id") != tranche["id"]] + [tranche]
    manifest.pop("dynamic_assignment", None)
    manifest.pop("manifest_payload_sha256", None)
    manifest["manifest_payload_sha256"] = canonical_hash(manifest)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--checkpoint", type=Path, default=CHECKPOINT)
    parser.add_argument("--run-id", default=RUN_ID)
    parser.add_argument("--tranche-audit", type=Path, required=True)
    args = parser.parse_args()
    value = ingest(args.checkpoint, args.run_id, args.tranche_audit)
    MANIFEST.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    print(f"updated {MANIFEST}: {value['counts']['closed']}/47 closed")


if __name__ == "__main__":
    main()

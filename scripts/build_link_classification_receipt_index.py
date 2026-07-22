#!/usr/bin/env python3
"""Build a hash-bound census of every active-frontier result receipt."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DURABLE = ROOT / "artifacts/portfolio/frontier-manifest-20of47-snapshot.json"
CANDIDATE = ROOT / "artifacts/portfolio/frontier-manifest-26of47-seven-orbit-snapshot.json"
OUTPUT = ROOT / "artifacts/classification/exhaustive-link-v1/receipt-index.json"
RETRY_CHECKPOINT = ROOT / "artifacts/sequential-frontier-sweep/sequential-open-frontier-32-v5-20260722-registration-retry-01/checkpoint.json"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verified_receipt(record: dict[str, object] | None) -> dict[str, object] | None:
    if not record:
        return None
    relative = str(record["path"])
    path = ROOT / relative
    if not path.is_file():
        raise ValueError(f"missing receipt: {relative}")
    actual = sha(path)
    if actual != record["sha256"]:
        raise ValueError(f"receipt hash mismatch: {relative}")
    return {"path": relative, "sha256": actual, "bytes": path.stat().st_size}


def proof_location(outcome: dict[str, object]) -> dict[str, object] | None:
    replay = outcome.get("replay_receipt")
    if not replay:
        return None
    value = json.loads((ROOT / replay["path"]).read_text(encoding="utf-8"))
    proof = value.get("proof")
    if not isinstance(proof, dict):
        return None
    recorded_path = Path(str(proof["path"]))
    candidates = [recorded_path]
    if recorded_path.is_absolute() and "/workspace/" in str(recorded_path):
        relative = str(recorded_path).split("/workspace/", 1)[1]
        candidates.append(ROOT / relative)
    available = next((path for path in candidates if path.is_file()), None)
    result = {
        "recorded_path": str(recorded_path),
        "sha256": proof["sha256"],
        "available_on_this_host": available is not None,
        "location_class": "local" if available is not None else "external-live-host",
    }
    if available is not None:
        actual = sha(available)
        if actual != proof["sha256"]:
            raise ValueError(f"proof hash mismatch: {available}")
        result["resolved_path"] = str(available)
        result["bytes"] = available.stat().st_size
    return result


def build() -> dict[str, object]:
    durable = json.loads(DURABLE.read_text(encoding="utf-8"))
    candidate = json.loads(CANDIDATE.read_text(encoding="utf-8"))
    durable_closed = {
        row["id"] for row in durable["nodes"] if row["final_coverage_status"] != "open"
    }
    candidate_closed = {
        row["id"] for row in candidate["nodes"] if row["final_coverage_status"] != "open"
    }
    promoted = candidate_closed - durable_closed
    if len(durable_closed) != 20 or len(candidate_closed) != 26 or len(promoted) != 6:
        raise ValueError("unexpected 20-to-26 ledger transition")

    nodes = []
    for node in candidate["nodes"]:
        outcomes = []
        for outcome in node["outcomes"]:
            outcomes.append({
                "run_id": outcome["run_id"],
                "method": outcome["method"],
                "status": outcome["status"],
                "cnf_sha256": outcome.get("cnf_sha256"),
                "proof_sha256": outcome.get("proof_sha256"),
                "result_receipt": verified_receipt(outcome.get("result_receipt")),
                "cnf_audit_receipt": verified_receipt(outcome.get("independent_audit_receipt")),
                "replay_receipt": verified_receipt(outcome.get("replay_receipt")),
                "proof_material": proof_location(outcome),
            })
        if node["id"] in durable_closed:
            tier = "durable_global_preexisting"
        elif node["id"] in promoted:
            tier = "promoted_global_in_this_workstream"
        elif outcomes:
            tier = "measured_open"
        else:
            tier = "unmeasured_open"
        nodes.append({
            "id": node["id"],
            "kind": node["kind"],
            "coverage_status": node["final_coverage_status"],
            "receipt_tier": tier,
            "outcomes": outcomes,
        })

    discoveries = []
    for leaf in ("t-16", "t-17"):
        base = ROOT / "artifacts/discoveries" / f"link-orbit-{leaf}"
        orbit = json.loads((base / "orbit.json").read_text(encoding="utf-8"))
        audit = json.loads((base / "orbit-audit.json").read_text(encoding="utf-8"))
        if audit["status"] != "valid" or audit["canonical_sha256"] != orbit["canonical_sha256"]:
            raise ValueError(f"invalid orbit audit: {leaf}")
        discoveries.append({
            "leaf_id": leaf,
            "status": "validated_link_orbit_not_frontier_closure",
            "canonical_sha256": orbit["canonical_sha256"],
            "orbit_size": orbit["orbit_size"],
            "stabilizer_order": orbit["stabilizer_order"],
            "orbit_receipt": {"path": str(base.relative_to(ROOT) / "orbit.json"), "sha256": sha(base / "orbit.json")},
            "audit_receipt": {"path": str(base.relative_to(ROOT) / "orbit-audit.json"), "sha256": sha(base / "orbit-audit.json")},
        })

    retry = json.loads(RETRY_CHECKPOINT.read_text(encoding="utf-8"))
    duplicate_receipts = []
    for result in retry["results"]:
        if result["leaf_id"] not in {"t-7", "t-8", "t-9"}:
            continue
        folder = Path(result["path"])
        duplicate_receipts.append({
            "leaf_id": result["leaf_id"],
            "status": result["status"],
            "cnf_sha256": result["cnf_sha256"],
            "proof_sha256": result["proof"]["sha256"],
            "result_receipt": verified_receipt({
                "path": str(folder / "result.json"),
                "sha256": sha(ROOT / folder / "result.json"),
            }),
            "cnf_audit_receipt": verified_receipt({
                "path": str(folder / "cnf-audit.json"),
                "sha256": sha(ROOT / folder / "cnf-audit.json"),
            }),
            "replay_receipt": verified_receipt({
                "path": str(folder / "validation.json"),
                "sha256": sha(ROOT / folder / "validation.json"),
            }),
        })
    if [row["leaf_id"] for row in duplicate_receipts] != ["t-7", "t-8", "t-9"]:
        raise ValueError("retry duplicate receipt set changed")

    return {
        "schema_version": 1,
        "status": "valid",
        "durable_baseline": {"closed": 20, "open": 27, "manifest_sha256": sha(DURABLE)},
        "promoted_ledger": {"closed": 26, "open": 21, "manifest_sha256": sha(CANDIDATE)},
        "promoted_nodes": sorted(promoted),
        "duplicate_retry_nodes": {
            "nodes": ["t-7", "t-8", "t-9"],
            "classification": "duplicate verified closures; zero net-new coverage",
            "action": "retain original durable receipts; do not rerun for symmetry",
            "checkpoint": {"path": str(RETRY_CHECKPOINT.relative_to(ROOT)), "sha256": sha(RETRY_CHECKPOINT)},
            "receipts": duplicate_receipts,
        },
        "nodes": nodes,
        "structural_discoveries": discoveries,
        "counts": {
            "frontier_nodes": len(nodes),
            "durable_preexisting_closures": len(durable_closed),
            "promoted_new_closures": len(promoted),
            "promoted_global_closures": len(candidate_closed),
            "open": 47 - len(candidate_closed),
            "validated_new_orbits_not_closures": len(discoveries),
        },
        "claim_limit": "This indexes and hash-checks active receipts. It does not make the seven-orbit catalogue exhaustive or convert link discoveries into closed frontier nodes.",
    }


def main() -> None:
    value = build()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"indexed {len(value['nodes'])} nodes; promoted {len(value['promoted_nodes'])} closures")


if __name__ == "__main__":
    main()

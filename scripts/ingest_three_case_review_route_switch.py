#!/usr/bin/env python3
"""Record the frozen three-case review after two SAT orbit discoveries."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from build_certificate_portfolio import canonical_hash


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = Path("artifacts/portfolio/frontier-manifest-v1.json")
CHECKPOINT = Path("artifacts/sequential-frontier-sweep/sequential-three-case-review-v7-20260722/checkpoint.json")
TRANCHE_MANIFEST = Path("artifacts/experiments/sequential-three-case-review-v7-20260722/manifest.json")
BATCH_AUDIT = Path("artifacts/classification/exhaustive-link-v1/three-case-review-new-orbits-independent-audit.json")
CATALOG = Path("artifacts/discoveries/link-orbit-catalog-9.json")
INDEX = Path("artifacts/classification/exhaustive-link-v1/certificate-index-32of47.json")
RUN_ID = "sequential-three-case-review-v7-20260722"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def receipt(path: Path) -> dict[str, object]:
    absolute = ROOT / path
    return {"path": str(path), "sha256": sha(absolute), "bytes": absolute.stat().st_size}


def ingest() -> dict[str, object]:
    manifest = json.loads((ROOT / MANIFEST).read_text())
    checkpoint = json.loads((ROOT / CHECKPOINT).read_text())
    tranche = json.loads((ROOT / TRANCHE_MANIFEST).read_text())
    batch = json.loads((ROOT / BATCH_AUDIT).read_text())
    catalog = json.loads((ROOT / CATALOG).read_text())
    index = json.loads((ROOT / INDEX).read_text())
    expected = ["t-16", "t-17", "s-r0-1"]
    if [row["leaf_id"] for row in checkpoint["results"]] != expected:
        raise ValueError("checkpoint is not the exact frozen three-case order")
    if sha(ROOT / TRANCHE_MANIFEST) != checkpoint["manifest_sha256"]:
        raise ValueError("checkpoint/manifest hash mismatch")
    if tranche["seconds_per_run"] != 60 or tranche["method"] != "sequential":
        raise ValueError("frozen protocol changed")
    if batch.get("status") != "valid-distinct-new-link-orbits" or batch.get("candidate_count") != 2:
        raise ValueError("independent new-orbit audit missing")
    candidates = {row["result"]["sha256"]: row for row in batch["candidates"]}
    catalog_canonicals = {row["canonical_sha256"] for row in catalog["orbits"]}
    if catalog["orbit_count"] != 9 or manifest["active_link_catalog"]["sha256"] != sha(ROOT / CATALOG):
        raise ValueError("nine-orbit catalog is not active")
    if manifest["predecessor_link_blocker"]["sha256"] != tranche["input_sha256"][tranche["blocking_cnf"]]:
        raise ValueError("seven-orbit predecessor binding mismatch")
    nodes = {row["id"]: row for row in manifest["nodes"]}
    sources = []
    for result in checkpoint["results"]:
        node = nodes[result["leaf_id"]]
        folder = Path(result["path"])
        result_path, build_path, audit_path = (folder / name for name in ("result.json", "build.json", "cnf-audit.json"))
        stored = json.loads((ROOT / result_path).read_text())
        build = json.loads((ROOT / build_path).read_text())
        semantic = json.loads((ROOT / audit_path).read_text())
        if build["blocker_sha256"] != manifest["predecessor_link_blocker"]["sha256"]:
            raise ValueError(f"{node['id']}: result not bound to seven-orbit predecessor")
        if semantic.get("status") != "valid" or semantic.get("cnf_sha256") != result["cnf_sha256"]:
            raise ValueError(f"{node['id']}: CNF audit disagreement")
        outcome = {
            "run_id": RUN_ID,
            "method": "sequential",
            "runtime_seconds": result["solver_elapsed_seconds"],
            "cpu_seconds": result["solver_elapsed_seconds"],
            "seconds_cap": 60,
            "cnf_encoding_revision": f"{RUN_ID}:sequential:schema-2:seven-orbit-blocker",
            "cnf_sha256": result["cnf_sha256"],
            "blocker_sha256_at_execution": build["blocker_sha256"],
            "result_receipt": receipt(result_path),
            "independent_cnf_audit_receipt": receipt(audit_path),
        }
        if stored["status"] == "SAT_NEW_ORBIT":
            candidate = candidates.get(sha(ROOT / result_path))
            if not candidate or candidate["canonical_sha256"] not in catalog_canonicals:
                raise ValueError(f"{node['id']}: candidate is not independently audited and catalogued")
            outcome.update({
                "status": "provisional_sat",
                "classification": "blocked_by_newly_discovered_orbit",
                "canonical_link_sha256": candidate["canonical_sha256"],
                "link_witness_receipt": candidate["witness"],
                "independent_orbit_audit_receipt": receipt(BATCH_AUDIT),
                "local_claim": "Valid new point-link orbit under the seven-orbit blocker; now included in the nine-orbit blocker. It is not a 40-cover or a closed frontier leaf.",
            })
        elif stored["status"] == "UNKNOWN":
            outcome.update({
                "status": "unknown",
                "classification": "fixed_cap_timeout_under_predecessor_blocker",
                "local_claim": "First measurement reached the unchanged 60-second cap; no mathematical conclusion.",
            })
        else:
            raise ValueError(f"unexpected result status for {node['id']}: {stored['status']}")
        node["outcomes"] = [row for row in node["outcomes"] if row.get("run_id") != RUN_ID] + [outcome]
        node["outcomes"].sort(key=lambda row: (row.get("run_id", ""), row.get("method", "")))
        sources.append(receipt(result_path))

    # Normalize one historical bookkeeping error: this immutable sequential
    # receipt found the fifth orbit, but an early benchmark ingestion labeled
    # it UNKNOWN.  The catalog and witness receipts already validate it.
    legacy_node = nodes["s-r1-3"]
    legacy = next(row for row in legacy_node["outcomes"] if
                  row.get("run_id") == "cardinality-encoding-20-leaf-20260722" and
                  row.get("method") == "sequential")
    legacy_result_path = Path(legacy["result_receipt"]["path"])
    legacy_result = json.loads((ROOT / legacy_result_path).read_text())
    legacy_folder = legacy_result_path.parent
    legacy_validation_path = legacy_folder / "validation.json"
    legacy_witness_path = legacy_folder / "witness.txt"
    legacy_validation = json.loads((ROOT / legacy_validation_path).read_text())
    if legacy_result.get("status") != "SAT_NEW_ORBIT" or legacy_validation.get("status") != "valid-new-link-orbit":
        raise ValueError("s-r1-3 immutable receipt is not the expected fifth-orbit discovery")
    if legacy_validation["witness_sha256"] != sha(ROOT / legacy_witness_path):
        raise ValueError("s-r1-3 witness hash mismatch")
    if legacy_validation["canonical_sha256"] not in catalog_canonicals:
        raise ValueError("s-r1-3 fifth orbit is absent from the active catalog")
    legacy.update({
        "status": "provisional_sat",
        "classification": "blocked_by_newly_discovered_orbit",
        "canonical_link_sha256": legacy_validation["canonical_sha256"],
        "link_witness_receipt": receipt(legacy_witness_path),
        "link_validation_receipt": receipt(legacy_validation_path),
        "local_claim": "Validated fifth point-link orbit now included in the active blocker; not a 40-cover or a closed frontier leaf.",
    })

    if manifest["counts"] != {"total": 47, "closed": 32, "open": 15}:
        raise ValueError("route-switch tranche must not change the global ledger")
    incident = index["new_orbit_extension_evidence"]
    review = {
        "id": f"{RUN_ID}-segment-01-route-switch",
        "status": "reviewed_route_switch_new_orbits",
        "source_results": sources,
        "completed_solver_runs": 3,
        "protocol": {"method": "sequential", "seconds_per_run": 60, "ordered_nodes": expected},
        "outcomes": {"new_link_orbits": 2, "fixed_cap_timeouts": 1, "certified_unsat": 0},
        "newly_closed_nodes": [],
        "cumulative_closed_out_of_47": "32/47",
        "independent_orbit_audit": receipt(BATCH_AUDIT),
        "nine_orbit_catalog": receipt(CATALOG),
        "preserved_t16_proof_incident": incident["t-16_incident"],
        "accepted_t16_external_replacement": incident["t-16_valid_external_replacement"],
        "bookkeeping_correction": "s-r1-3 sequential immutable SAT_NEW_ORBIT receipt was normalized from an erroneous stored UNKNOWN label to provisional_sat; no closure count changed.",
        "claim_limit": "Two point-link orbits were discovered and one case timed out. None is a global closure; the ledger remains 32/47.",
    }
    manifest["tranches"] = [row for row in manifest["tranches"] if row.get("id") != review["id"]] + [review]
    manifest.pop("manifest_payload_sha256", None)
    manifest["manifest_payload_sha256"] = canonical_hash(manifest)
    return manifest


def main() -> None:
    value = ingest()
    output = ROOT / MANIFEST
    output.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    print("recorded route switch: two new orbits, one timeout, ledger 32/47")


if __name__ == "__main__":
    main()

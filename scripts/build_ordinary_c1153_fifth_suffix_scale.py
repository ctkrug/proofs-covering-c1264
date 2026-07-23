#!/usr/bin/env python3
"""Freeze the complete fifth-level suffix universe and resumable segment map."""

from __future__ import annotations

import hashlib
import json
import math
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "artifacts/classification/ordinary-c1153-v1/hard-tail-fifth-split"
MANIFEST_PATH = BASE / "manifest.json"
DISCRIMINATOR_PATH = BASE / "discriminator-5s-summary.json"
SEGMENT_SIZE = 256
PROJECTED_MEAN_PROOF_BYTES = 135445.6888888889
STORAGE_LIMIT_BYTES = 6 * 1024**3
MIN_FREE_RESERVE_BYTES = 8 * 1024**3


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def leaf_id(parent_id: str, index: int) -> str:
    return f"{parent_id}-fifth-{index:03d}"


def build() -> dict[str, object]:
    manifest = json.loads(MANIFEST_PATH.read_text())
    discriminator = json.loads(DISCRIMINATOR_PATH.read_text())
    measured = {row["leaf_id"] for row in discriminator["outcomes"]}
    universe = []
    parent_counts = {}
    for parent in manifest["parents"]:
        start = parent["branch_count"] // 4
        rows = []
        for index in range(start, parent["branch_count"]):
            relative = index / parent["branch_count"]
            position = "first_quartile" if relative < 0.5 else "middle_quartile" if relative < 0.75 else "last_quartile"
            rows.append({"leaf_id": leaf_id(parent["id"], index), "parent_id": parent["id"], "index": index, "position": position})
        universe.extend(rows)
        parent_counts[parent["id"]] = len(rows)
    if len(universe) != 32645 or len({row["leaf_id"] for row in universe}) != 32645:
        raise ValueError("suffix universe changed")
    suffix_ids = {row["leaf_id"] for row in universe}
    excluded = sorted(suffix_ids & measured)
    if len(excluded) != 48:
        raise ValueError("expected 48 measured discriminator leaves in suffix universe")
    pending = [row for row in universe if row["leaf_id"] not in measured]
    seed = sha(MANIFEST_PATH)
    pending.sort(key=lambda row: hashlib.sha256(f"{seed}:{row['leaf_id']}".encode()).hexdigest())
    if len(pending) != 32597:
        raise ValueError("pending suffix count mismatch")
    segments = []
    for number in range(math.ceil(len(pending) / SEGMENT_SIZE)):
        rows = pending[number * SEGMENT_SIZE:(number + 1) * SEGMENT_SIZE]
        segments.append({
            "segment": number,
            "count": len(rows),
            "leaf_ids": [row["leaf_id"] for row in rows],
            "selection_sha256": hashlib.sha256(("\n".join(row["leaf_id"] for row in rows) + "\n").encode()).hexdigest(),
        })
    free_bytes = shutil.disk_usage(ROOT).free
    projected = round(len(pending) * PROJECTED_MEAN_PROOF_BYTES)
    if projected > STORAGE_LIMIT_BYTES or free_bytes - projected < MIN_FREE_RESERVE_BYTES:
        raise ValueError("full suffix projection exceeds storage policy")
    route = {
        "schema_version": 1,
        "status": "FROZEN_NOT_RUN",
        "fifth_manifest": {"path": str(MANIFEST_PATH.relative_to(ROOT)), "sha256": sha(MANIFEST_PATH)},
        "discriminator_summary": {"path": str(DISCRIMINATOR_PATH.relative_to(ROOT)), "sha256": sha(DISCRIMINATOR_PATH)},
        "accounting": {
            "suffix_universe_including_measured": 32645,
            "measured_discriminator_leaves_excluded": 48,
            "pending_scale_workload": 32597,
            "note": "The requested 32,645 is the suffix universe. Excluding every already measured suffix leaf necessarily leaves 32,597 solver jobs.",
        },
        "selection_rule": "For every one of 384 fourth parents, include fifth indices floor(branch_count/4) through branch_count-1. Exclude all already measured discriminator leaves; order remaining leaves by SHA-256 of manifest hash plus leaf id.",
        "parent_suffix_counts": parent_counts,
        "excluded_measured_leaf_ids": excluded,
        "segment_size": SEGMENT_SIZE,
        "segment_count": len(segments),
        "segments": segments,
        "fixed_protocol": {"solver": "CaDiCaL 3.0.1", "seconds_cap": 5, "parallelism": 4, "proof_checker": "drat-trim"},
        "storage_plan": {
            "representation": "Cached third-level parent CNF plus inherited fourth and fifth unit recipes; no full child CNF persists.",
            "deterministic_proof_path": "segments/segment-NNNN/<leaf-id>/proof.drat.gz",
            "compression": "gzip level 6, empty filename, mtime 0",
            "projected_mean_compressed_proof_bytes": PROJECTED_MEAN_PROOF_BYTES,
            "projected_pending_proof_bytes": projected,
            "storage_limit_bytes": STORAGE_LIMIT_BYTES,
            "minimum_free_reserve_bytes": MIN_FREE_RESERVE_BYTES,
            "free_bytes_at_freeze": free_bytes,
            "receipt_policy": "Each segment has a frozen manifest, runner receipt, and independent reconstruction/replay audit before continuation.",
        },
        "continuation_gate": "Replay success must be 100%; timeout rate and mean proof bytes must remain consistent with the discriminator; projected total must remain within storage policy; SAT or any audit disagreement stops the route.",
        "claim_limit": "This freezes the suffix workload only. No fourth parent closes unless every fifth child, including the deferred prefix, later has an audited terminal certificate.",
    }
    route_path = BASE / "suffix-scale-manifest.json"
    route_path.write_text(json.dumps(route, indent=2, sort_keys=True) + "\n")
    first = segments[0]
    first_manifest = {
        "schema_version": 1,
        "status": "FROZEN_NOT_RUN",
        "route_manifest": {"path": str(route_path.relative_to(ROOT)), "sha256": sha(route_path)},
        "segment": 0,
        "selected": first["count"],
        "selection_sha256": first["selection_sha256"],
        "leaf_ids": first["leaf_ids"],
        "fixed_protocol": route["fixed_protocol"],
        "artifact_budget": {"compressed_proof_bytes": 64 * 1024**2, "worst_solver_wall_seconds": first["count"] * 5 / 4},
        "claim_limit": "First projection-validation segment only.",
    }
    segment_dir = BASE / "segments/segment-0000"
    segment_dir.mkdir(parents=True, exist_ok=False)
    segment_path = segment_dir / "manifest.json"
    segment_path.write_text(json.dumps(first_manifest, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"route": str(route_path), "suffix_universe": 32645, "excluded": 48, "pending": len(pending), "segments": len(segments), "segment_0": first["count"], "projected_bytes": projected, "free_bytes": free_bytes}, sort_keys=True))
    return route


if __name__ == "__main__":
    build()

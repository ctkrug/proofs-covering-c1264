#!/usr/bin/env python3
"""Run resumable sequential-only short-cap units over a hash-bound frontier."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

import run_cardinality_encoding_benchmark as shared


ROOT = Path(__file__).resolve().parents[1]


def verify(manifest_path: Path) -> dict[str, object]:
    superseded = manifest_path.parent / "SUPERSEDED.json"
    if superseded.is_file():
        reason = json.loads(superseded.read_text(encoding="utf-8")).get("reason", "manifest superseded")
        raise ValueError(f"refusing superseded sweep manifest: {reason}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("method") != "sequential" or len(manifest.get("leaves", [])) != 32:
        raise ValueError("manifest must specify sequential over exactly 32 audited open leaves")
    if len({row["id"] for row in manifest["leaves"]}) != 32:
        raise ValueError("duplicate leaf ID")
    for path_text, expected in manifest["input_sha256"].items():
        path = shared.validate_under_root(Path(path_text))
        if shared.sha(path) != expected:
            raise ValueError(f"input hash mismatch: {path_text}")
    summary = json.loads(shared.validate_under_root(Path(manifest["frontier_summary"])).read_text(encoding="utf-8"))
    frontier = {
        (int(row["root_index"]), int(row["secondary_index"]), None): row["result_sha256"]
        for row in summary["open_secondary_cases"]
    }
    frontier.update({
        (int(row["root_index"]), int(row["secondary_index"]), int(row["tertiary_index"])): row["result_sha256"]
        for row in summary["open_tertiary_cases"]
    })
    for leaf in manifest["leaves"]:
        tertiary = leaf.get("tertiary_index")
        key = (int(leaf["root_index"]), int(leaf["secondary_index"]), None if tertiary is None else int(tertiary))
        if frontier.get(key) != leaf["inherited_result_sha256"]:
            raise ValueError(f"leaf is not bound to the frozen frontier: {leaf['id']}")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--progress", type=Path, required=True)
    parser.add_argument("--units-per-invocation", type=int, default=8)
    args = parser.parse_args()
    if not shared.SAFE_RUN_ID.fullmatch(args.run_id) or args.units_per_invocation < 1:
        raise ValueError("unsafe run configuration")
    manifest_path = shared.validate_under_root(args.manifest)
    checkpoint_path = shared.validate_under_root(args.checkpoint)
    progress_path = shared.validate_under_root(args.progress)
    manifest = verify(manifest_path)
    manifest_sha = shared.sha(manifest_path)
    output_root = ROOT / "artifacts/sequential-frontier-sweep" / args.run_id
    output_root.mkdir(parents=True, exist_ok=True)
    prior = json.loads(checkpoint_path.read_text(encoding="utf-8")) if checkpoint_path.is_file() else {
        "schema_version": 1, "manifest_sha256": manifest_sha, "completed": [], "results": [],
        "stopped": False, "stop_reason": "",
    }
    if prior["manifest_sha256"] != manifest_sha:
        raise ValueError("checkpoint belongs to a different manifest")
    completed = set(prior["completed"])
    attempted = 0
    for leaf in manifest["leaves"]:
        unit_id = f"{leaf['id']}--sequential"
        if unit_id in completed:
            continue
        if attempted >= args.units_per_invocation or prior["stopped"]:
            break
        final_dir = output_root / str(leaf["id"]) / "sequential"
        if final_dir.exists():
            shutil.rmtree(final_dir)
        final_dir.mkdir(parents=True)
        result = shared.run_one(
            leaf, "sequential", final_dir,
            shared.validate_under_root(Path(manifest["blocking_cnf"])),
            shared.validate_under_root(Path(manifest["catalog"])),
            Path(manifest["solver"]),
            shared.validate_under_root(Path(manifest["drat_trim"])),
            int(manifest["seconds_per_run"]), manifest_sha,
        )
        result["path"] = str(final_dir.relative_to(ROOT))
        prior["completed"].append(unit_id)
        prior["results"].append(result)
        completed.add(unit_id)
        attempted += 1
        proofs = [int(row["proof"]["bytes"]) for row in prior["results"] if isinstance(row.get("proof"), dict)]
        projected = 0 if not proofs else int(sum(proofs) / len(proofs) * len(manifest["leaves"]))
        prior["projected_proof_bytes"] = projected
        if projected > int(manifest["maximum_projected_proof_bytes"]):
            prior["stopped"] = True
            prior["stop_reason"] = "projected proof storage exceeds predeclared cap"
        shared.atomic_json(checkpoint_path, prior)
        shared.atomic_json(progress_path, {
            "completed_units": len(prior["completed"]),
            "total_units": len(manifest["leaves"]),
            "complete": len(prior["completed"]) == len(manifest["leaves"]) or prior["stopped"],
            "correctness_checks_passed": True,
            "decision_value_active": not prior["stopped"],
            "artifact_bytes": shared.artifact_bytes(output_root),
            "message": prior["stop_reason"],
        })
    if not progress_path.is_file():
        shared.atomic_json(progress_path, {
            "completed_units": len(prior["completed"]), "total_units": len(manifest["leaves"]),
            "complete": False, "correctness_checks_passed": True,
            "decision_value_active": True, "artifact_bytes": shared.artifact_bytes(output_root), "message": "",
        })
    print(json.dumps({"completed": len(prior["completed"]), "total": len(manifest["leaves"]), "stopped": prior["stopped"]}, sort_keys=True))


if __name__ == "__main__":
    main()

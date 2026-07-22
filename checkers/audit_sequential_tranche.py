#!/usr/bin/env python3
"""Replay and audit every UNSAT claim in one frozen sequential checkpoint."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("checkpoint", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, default=Path("artifacts/portfolio/frontier-manifest-v1.json"))
    parser.add_argument("--checker", type=Path, default=Path("toolchains/drat-trim/drat-trim"))
    args = parser.parse_args()
    checkpoint_path = args.checkpoint if args.checkpoint.is_absolute() else ROOT / args.checkpoint
    manifest_path = args.manifest if args.manifest.is_absolute() else ROOT / args.manifest
    checker_path = args.checker if args.checker.is_absolute() else ROOT / args.checker
    output_path = args.output if args.output.is_absolute() else ROOT / args.output

    checkpoint = json.loads(checkpoint_path.read_text())
    manifest = json.loads(manifest_path.read_text())
    active_blocker = manifest["active_link_blocker"]["sha256"]
    rows = []
    for result in checkpoint["results"]:
        folder = ROOT / result["path"]
        build_path, audit_path, result_path = (folder / name for name in ("build.json", "cnf-audit.json", "result.json"))
        build, audit, stored = (json.loads(path.read_text()) for path in (build_path, audit_path, result_path))
        if build["blocker_sha256"] != active_blocker:
            raise ValueError(f"{result['leaf_id']}: stale blocker")
        if audit["status"] != "valid" or audit["cnf_sha256"] != result["cnf_sha256"]:
            raise ValueError(f"{result['leaf_id']}: CNF audit disagreement")
        if sha(folder / "instance.cnf") != result["cnf_sha256"]:
            raise ValueError(f"{result['leaf_id']}: reconstructed CNF hash disagreement")
        row = {
            "leaf_id": result["leaf_id"],
            "status": result["status"],
            "active_blocker_sha256": active_blocker,
            "build_sha256": sha(build_path),
            "cnf_audit_sha256": sha(audit_path),
            "result_sha256": sha(result_path),
            "cnf_sha256": result["cnf_sha256"],
        }
        if result["status"] == "UNSAT_VERIFIED":
            proof_path = folder / "proof.drat"
            if sha(proof_path) != result["proof"]["sha256"]:
                raise ValueError(f"{result['leaf_id']}: proof hash disagreement")
            replay = subprocess.run(
                [str(checker_path), str(folder / "instance.cnf"), str(proof_path)],
                text=True, capture_output=True, check=False,
            )
            if replay.returncode != 0 or "s VERIFIED" not in replay.stdout:
                raise ValueError(f"{result['leaf_id']}: independent replay failed")
            row.update({
                "proof_sha256": sha(proof_path),
                "proof_bytes": proof_path.stat().st_size,
                "independent_replay": "verified",
                "replay_exit_code": replay.returncode,
            })
        elif result["status"] != "UNKNOWN":
            raise ValueError(f"{result['leaf_id']}: unexpected status {result['status']}")
        rows.append(row)

    payload = {
        "schema_version": 1,
        "status": "valid",
        "claim_limit": "Audits only this frozen tranche; global closure requires portfolio ingestion and frontier audit.",
        "checkpoint": {"path": str(checkpoint_path.relative_to(ROOT)), "sha256": sha(checkpoint_path)},
        "manifest_before_ingestion": {"path": str(manifest_path.relative_to(ROOT)), "sha256": sha(manifest_path)},
        "active_blocker_sha256": active_blocker,
        "checker": {"path": str(checker_path.relative_to(ROOT)), "sha256": sha(checker_path)},
        "results": rows,
        "counts": {
            "total": len(rows),
            "unsat_independently_replayed": sum(row["status"] == "UNSAT_VERIFIED" for row in rows),
            "fixed_cap_timeouts": sum(row["status"] == "UNKNOWN" for row in rows),
        },
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(json.dumps(payload["counts"], sort_keys=True))


if __name__ == "__main__":
    main()

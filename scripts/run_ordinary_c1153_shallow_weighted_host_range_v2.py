#!/usr/bin/env python3
"""Run an exclusively assigned range with the audited v2 proposal backend."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "artifacts/classification/ordinary-c1153-v1/open-fifth-deficit-partition-v2/second-live-triple-gate-v1/shallow-weighted-scale-v1"
MANIFEST = BASE / "manifest.json"
SEGMENTS = BASE / "segments"
ASSIGNMENT = BASE / "hybrid-execution-v1/assignment-ledger.json"
UPGRADE = BASE / "backend-upgrade-v1/independent-audit.json"
RUNNER = ROOT / "scripts/run_ordinary_c1153_shallow_weighted_scale_v2.py"
BACKEND = ROOT / "scripts/ordinary_c1153_weighted_backend_v2.py"
CHECKER = ROOT / "checkers/audit_ordinary_c1153_shallow_weighted_scale.py"

EXPECTED_MANIFEST_SHA256 = "bb06b660377ad6cc8132c41132867602366210b918f940d12fb156bac078c3f4"
EXPECTED_ASSIGNMENT_SHA256 = "63b4456c59f9c6690bdfa10c5940acefb56786d591c1c525c1e2607722ca6b83"
EXPECTED_UPGRADE_AUDIT_SHA256 = "00e72053e44a2c9931f49a41252b9e89dd036db4397b4b3061ad39495c9906e2"
EXPECTED_RUNNER_SHA256 = "ec3492d733e4f1a9f10dbad634338a738e768128d7f9ba654a2256388429bb8d"
EXPECTED_BACKEND_SHA256 = "157044493dd014ff077cda1f51ba4f492ec74419dec4926c62cfeb00815fdba8"
EXPECTED_CHECKER_SHA256 = "161319de67fcae2c430101b70086d61af512046166d7a379abeff6e18ba2a68a"
MINIMUM_FREE_BYTES = 5_000_000_000


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def ref(path: Path) -> dict[str, str]:
    return {"path": str(path.relative_to(ROOT)), "sha256": sha(path)}


def compact(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def write_immutable(path: Path, value: object) -> None:
    raw = compact(value)
    if path.exists():
        if path.read_bytes() != raw:
            raise ValueError(f"refusing incompatible execution receipt: {path}")
        return
    temporary = path.with_suffix(".tmp")
    temporary.write_bytes(raw)
    os.replace(temporary, path)


def command(*args: str) -> None:
    subprocess.run(args, cwd=ROOT, check=True)


def clean_worktree() -> bool:
    result = subprocess.run(
        ("git", "status", "--porcelain"),
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return not result.stdout.strip()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--worker-id", required=True)
    parser.add_argument("--start", required=True, type=int)
    parser.add_argument("--stop", required=True, type=int)
    parser.add_argument("--branch", required=True)
    parser.add_argument("--workers", required=True, type=int)
    args = parser.parse_args()

    if args.workers < 1 or args.workers > 6:
        raise ValueError("v2 worker count must lie in 1..6")
    bindings = {
        MANIFEST: EXPECTED_MANIFEST_SHA256,
        ASSIGNMENT: EXPECTED_ASSIGNMENT_SHA256,
        UPGRADE: EXPECTED_UPGRADE_AUDIT_SHA256,
        RUNNER: EXPECTED_RUNNER_SHA256,
        BACKEND: EXPECTED_BACKEND_SHA256,
        CHECKER: EXPECTED_CHECKER_SHA256,
    }
    for path, expected in bindings.items():
        if sha(path) != expected:
            raise ValueError(f"v2 pinned artifact mismatch: {path}")
    upgrade = json.loads(UPGRADE.read_text())
    if upgrade["status"] != "VALID":
        raise ValueError("v2 upgrade audit is not valid")
    assignment = json.loads(ASSIGNMENT.read_text())
    owned = next(
        (
            row
            for row in assignment["assignments"]
            if row["worker_id"] == args.worker_id
        ),
        None,
    )
    if owned is None:
        raise ValueError("worker is absent from the audited assignment ledger")
    if (
        owned["branch"] != args.branch
        or args.start < owned["first_segment"]
        or args.stop > owned["last_segment"]
        or args.start > args.stop
    ):
        raise ValueError("requested v2 range exceeds immutable worker ownership")
    if not clean_worktree():
        raise ValueError("v2 worker refuses a dirty worktree")

    for number in range(args.start, args.stop + 1):
        segment_id = f"shallow-weighted-scale-{number:03d}"
        folder = SEGMENTS / segment_id
        if folder.exists():
            raise ValueError(f"{segment_id}: assigned segment exists; refusing rerun")
        if shutil.disk_usage(ROOT).free < MINIMUM_FREE_BYTES:
            raise RuntimeError(f"{segment_id}: free disk fell below 5 GB")
        started = time.perf_counter()
        command(
            sys.executable,
            str(RUNNER),
            "run",
            "--segment",
            str(number),
            "--workers",
            str(args.workers),
        )
        command(sys.executable, str(CHECKER), "--segment", str(number))

        summary_path = folder / "summary.json"
        audit_path = folder / "independent-audit.json"
        archive_path = folder / "outcomes.jsonl.gz"
        index_path = folder / "backend-v2/index.json"
        summary = json.loads(summary_path.read_text())
        audit = json.loads(audit_path.read_text())
        index = json.loads(index_path.read_text())
        if audit["status"] not in {"VALID", "VALID_GATE_FAILED"}:
            raise ValueError(f"{segment_id}: unchanged independent audit failed")
        if audit["summary_sha256"] != sha(summary_path):
            raise ValueError(f"{segment_id}: summary binding mismatch")
        if (
            audit["selected"] != summary["selected"]
            or audit["independently_checked_weighted_formulas"]
            != summary["weighted_certificate_count"]
        ):
            raise ValueError(f"{segment_id}: formula/checker count mismatch")
        if (
            summary["backend_v2"]["index"]["sha256"] != sha(index_path)
            or index["generator"]["sha256"] != EXPECTED_RUNNER_SHA256
            or index["backend"]["sha256"] != EXPECTED_BACKEND_SHA256
            or sum(row["case_count"] for row in index["chunks"]) != summary["selected"]
        ):
            raise ValueError(f"{segment_id}: v2 chunk-index binding mismatch")
        execution = {
            "schema_version": 1,
            "status": "VALID_V2_SEGMENT_PENDING_CENTRAL_IMPORT",
            "worker_id": args.worker_id,
            "owned_range": [owned["first_segment"], owned["last_segment"]],
            "segment_number": number,
            "segment_id": segment_id,
            "formula_count": summary["selected"],
            "weighted_certificate_count": summary["weighted_certificate_count"],
            "open_no_certificate_count": summary["open_no_certificate_count"],
            "v2_worker_processes": args.workers,
            "wall_seconds_including_generation_and_independent_audit": (
                time.perf_counter() - started
            ),
            "bindings": {
                "assignment_ledger": ref(ASSIGNMENT),
                "frozen_manifest": ref(MANIFEST),
                "backend_upgrade_audit": ref(UPGRADE),
                "v2_generator": ref(RUNNER),
                "v2_backend": ref(BACKEND),
                "unchanged_checker": ref(CHECKER),
                "summary": ref(summary_path),
                "independent_audit": ref(audit_path),
                "outcome_archive": ref(archive_path),
                "v2_chunk_index": ref(index_path),
            },
        }
        receipt_path = folder / "backend-v2/execution-receipt.json"
        write_immutable(receipt_path, execution)

        command("git", "add", str(folder.relative_to(ROOT)))
        command(
            "git",
            "commit",
            "-m",
            f"Record {args.worker_id} v2 shallow weighted segment {number:03d}",
        )
        command("git", "push", "origin", f"HEAD:{args.branch}")
        print(
            json.dumps(
                {
                    "worker_id": args.worker_id,
                    "segment_id": segment_id,
                    "selected": summary["selected"],
                    "certified": summary["weighted_certificate_count"],
                    "open": summary["open_no_certificate_count"],
                    "audit_status": audit["status"],
                    "v2_workers": args.workers,
                    "wall_seconds": execution[
                        "wall_seconds_including_generation_and_independent_audit"
                    ],
                    "commit_pushed": True,
                },
                sort_keys=True,
            ),
            flush=True,
        )


if __name__ == "__main__":
    main()

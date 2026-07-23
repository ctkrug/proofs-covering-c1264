#!/usr/bin/env python3
"""Run one exclusively assigned shallow-weighted segment range.

Each successful segment is independently audited, committed, and pushed before
the next segment starts.  Open formulas remain open; any certificate/checker
disagreement or resource failure stops the worker.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "artifacts/classification/ordinary-c1153-v1/open-fifth-deficit-partition-v2/second-live-triple-gate-v1/shallow-weighted-scale-v1"
MANIFEST = BASE / "manifest.json"
SEGMENTS = BASE / "segments"
RUNNER = ROOT / "scripts/run_ordinary_c1153_shallow_weighted_scale.py"
CHECKER = ROOT / "checkers/audit_ordinary_c1153_shallow_weighted_scale.py"

EXPECTED_MANIFEST_SHA256 = "bb06b660377ad6cc8132c41132867602366210b918f940d12fb156bac078c3f4"
EXPECTED_RUNNER_SHA256 = "8165521d5440cc108335a10b380d53882478edd3d6bd19fdbd23488413c28920"
EXPECTED_CHECKER_SHA256 = "161319de67fcae2c430101b70086d61af512046166d7a379abeff6e18ba2a68a"
MINIMUM_FREE_BYTES = 5_000_000_000


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


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
    args = parser.parse_args()

    if not (0 <= args.start <= args.stop < 85):
        raise ValueError("assigned segment range must lie within 000..084")
    if sha(MANIFEST) != EXPECTED_MANIFEST_SHA256:
        raise ValueError("frozen manifest hash mismatch")
    if sha(RUNNER) != EXPECTED_RUNNER_SHA256 or sha(CHECKER) != EXPECTED_CHECKER_SHA256:
        raise ValueError("runner/checker revision mismatch")
    if not clean_worktree():
        raise ValueError("worker refuses a dirty worktree")

    for number in range(args.start, args.stop + 1):
        segment_id = f"shallow-weighted-scale-{number:03d}"
        folder = SEGMENTS / segment_id
        if folder.exists():
            raise ValueError(f"{segment_id}: assigned segment already exists; refusing rerun")
        if shutil.disk_usage(ROOT).free < MINIMUM_FREE_BYTES:
            raise RuntimeError(f"{segment_id}: free disk fell below 5 GB")

        command(sys.executable, str(RUNNER), "run", "--segment", str(number))
        command(sys.executable, str(CHECKER), "--segment", str(number))

        summary = json.loads((folder / "summary.json").read_text())
        audit = json.loads((folder / "independent-audit.json").read_text())
        if audit["status"] not in {"VALID", "VALID_GATE_FAILED"}:
            raise ValueError(f"{segment_id}: independent audit failed")
        if audit["summary_sha256"] != sha(folder / "summary.json"):
            raise ValueError(f"{segment_id}: summary binding mismatch")
        if (
            audit["independently_checked_weighted_formulas"]
            != summary["weighted_certificate_count"]
        ):
            raise ValueError(f"{segment_id}: certificate/checker count mismatch")
        if audit["selected"] != summary["selected"]:
            raise ValueError(f"{segment_id}: membership count mismatch")

        command("git", "add", str(folder.relative_to(ROOT)))
        command(
            "git",
            "commit",
            "-m",
            f"Record {args.worker_id} shallow weighted segment {number:03d}",
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
                    "commit_pushed": True,
                },
                sort_keys=True,
            ),
            flush=True,
        )


if __name__ == "__main__":
    main()

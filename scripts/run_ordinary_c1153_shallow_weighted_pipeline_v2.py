#!/usr/bin/env python3
"""Bounded one-segment producer/auditor pipeline for frozen shallow scale."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

import psutil


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "artifacts/classification/ordinary-c1153-v1/open-fifth-deficit-partition-v2/second-live-triple-gate-v1/shallow-weighted-scale-v1"
MANIFEST = BASE / "manifest.json"
SEGMENTS = BASE / "segments"
ASSIGNMENT = BASE / "hybrid-execution-v1/assignment-ledger.json"
UPGRADE = BASE / "backend-upgrade-v1/independent-audit.json"
RUNNER = ROOT / "scripts/run_ordinary_c1153_shallow_weighted_scale_v2.py"
BACKEND = ROOT / "scripts/ordinary_c1153_weighted_backend_v2.py"
CHECKER = ROOT / "checkers/audit_ordinary_c1153_shallow_weighted_scale.py"

EXPECTED = {
    MANIFEST: "bb06b660377ad6cc8132c41132867602366210b918f940d12fb156bac078c3f4",
    ASSIGNMENT: "63b4456c59f9c6690bdfa10c5940acefb56786d591c1c525c1e2607722ca6b83",
    UPGRADE: "00e72053e44a2c9931f49a41252b9e89dd036db4397b4b3061ad39495c9906e2",
    RUNNER: "ec3492d733e4f1a9f10dbad634338a738e768128d7f9ba654a2256388429bb8d",
    BACKEND: "157044493dd014ff077cda1f51ba4f492ec74419dec4926c62cfeb00815fdba8",
    CHECKER: "161319de67fcae2c430101b70086d61af512046166d7a379abeff6e18ba2a68a",
}
MINIMUM_FREE_BYTES = 5_000_000_000


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def ref(path: Path) -> dict[str, str]:
    return {"path": str(path.relative_to(ROOT)), "sha256": sha(path)}


def compact(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def write_immutable(path: Path, value: object) -> None:
    raw = compact(value)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != raw:
            raise ValueError(f"refusing incompatible pipeline receipt: {path}")
        return
    temporary = path.with_suffix(".tmp")
    temporary.write_bytes(raw)
    os.replace(temporary, path)


def swap_used_bytes() -> int:
    value = psutil.swap_memory()
    return int(value.used)


class Monitored:
    def __init__(self, command: list[str], metrics: Path):
        self.metrics_final = metrics
        handle = tempfile.NamedTemporaryFile(
            prefix="c1264-pipeline-time-", suffix=".txt", delete=False
        )
        handle.close()
        self.metrics_temporary = Path(handle.name)
        if platform.system() == "Darwin":
            wrapped = ["/usr/bin/time", "-lp", "-o", str(self.metrics_temporary), *command]
        else:
            wrapped = ["/usr/bin/time", "-v", "-o", str(self.metrics_temporary), *command]
        self.started = time.perf_counter()
        self.disk_before = shutil.disk_usage(ROOT).free
        self.swap_before = swap_used_bytes()
        self.peak_swap = self.swap_before
        self.peak_tree_rss = 0
        self.process = subprocess.Popen(wrapped, cwd=ROOT)
        self.root = psutil.Process(self.process.pid)
        self.done = threading.Event()
        self.monitor = threading.Thread(target=self._monitor, daemon=True)
        self.monitor.start()

    def _monitor(self) -> None:
        while not self.done.wait(0.2):
            try:
                processes = [self.root, *self.root.children(recursive=True)]
                rss = sum(item.memory_info().rss for item in processes if item.is_running())
                self.peak_tree_rss = max(self.peak_tree_rss, rss)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
            self.peak_swap = max(self.peak_swap, swap_used_bytes())

    def wait(self) -> dict[str, object]:
        code = self.process.wait()
        self.done.set()
        self.monitor.join()
        wall = time.perf_counter() - self.started
        if code:
            raise subprocess.CalledProcessError(code, self.process.args)
        self.metrics_final.parent.mkdir(parents=True, exist_ok=True)
        os.replace(self.metrics_temporary, self.metrics_final)
        return {
            "wall_seconds": wall,
            "peak_process_tree_rss_bytes": self.peak_tree_rss,
            "swap_used_before_bytes": self.swap_before,
            "peak_swap_used_bytes": self.peak_swap,
            "disk_free_before_bytes": self.disk_before,
            "disk_free_after_bytes": shutil.disk_usage(ROOT).free,
            "time_output": ref(self.metrics_final),
        }


def start(command: list[str], metrics: Path) -> Monitored:
    if shutil.disk_usage(ROOT).free < MINIMUM_FREE_BYTES:
        raise RuntimeError("free disk fell below 5 GB")
    return Monitored(command, metrics)


def validate_generation(number: int) -> tuple[Path, dict[str, object]]:
    folder = SEGMENTS / f"shallow-weighted-scale-{number:03d}"
    summary = json.loads((folder / "summary.json").read_text())
    index = json.loads((folder / "backend-v2/index.json").read_text())
    if (
        summary["status"] != "COMPLETE_PENDING_INDEPENDENT_AUDIT"
        or summary["selected"] != 2048
        or index["generator"]["sha256"] != EXPECTED[RUNNER]
        or index["backend"]["sha256"] != EXPECTED[BACKEND]
        or sum(row["case_count"] for row in index["chunks"]) != 2048
    ):
        raise ValueError(f"segment {number}: pending generation binding failed")
    return folder, summary


def validate_audit(number: int, folder: Path, summary: dict[str, object]) -> dict[str, object]:
    audit = json.loads((folder / "independent-audit.json").read_text())
    if (
        audit["status"] not in {"VALID", "VALID_GATE_FAILED"}
        or audit["selected"] != 2048
        or audit["summary_sha256"] != sha(folder / "summary.json")
        or audit["independently_checked_weighted_formulas"]
        != summary["weighted_certificate_count"]
    ):
        raise ValueError(f"segment {number}: unchanged independent audit failed")
    return audit


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--worker-id", required=True)
    parser.add_argument("--branch", required=True)
    parser.add_argument("--start", type=int, required=True)
    parser.add_argument("--stop", type=int, required=True)
    parser.add_argument("--formula-workers", type=int, default=2)
    args = parser.parse_args()

    for path, expected in EXPECTED.items():
        if sha(path) != expected:
            raise ValueError(f"pinned pipeline input changed: {path}")
    assignment = json.loads(ASSIGNMENT.read_text())
    owner = next(row for row in assignment["assignments"] if row["worker_id"] == args.worker_id)
    if (
        owner["branch"] != args.branch
        or args.start < owner["first_segment"]
        or args.stop > owner["last_segment"]
        or args.start > args.stop
    ):
        raise ValueError("pipeline range violates immutable ownership")
    if subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True).strip():
        raise ValueError("pipeline refuses a dirty worktree")
    for number in range(args.start, args.stop + 1):
        if (SEGMENTS / f"shallow-weighted-scale-{number:03d}").exists():
            raise ValueError(f"segment {number}: refusing rerun")

    current = args.start
    first_folder = SEGMENTS / f"shallow-weighted-scale-{current:03d}"
    generation = start(
        [sys.executable, str(RUNNER), "run", "--segment", str(current), "--workers", str(args.formula_workers)],
        first_folder / "backend-v2/generation-time.txt",
    )
    pending_metrics = generation.wait()

    while current <= args.stop:
        folder, summary = validate_generation(current)
        generation_receipt = {
            "schema_version": 1,
            "status": "PENDING_FULL_INDEPENDENT_AUDIT",
            "worker_id": args.worker_id,
            "segment_number": current,
            "formula_count": summary["selected"],
            "weighted_certificate_count": summary["weighted_certificate_count"],
            "open_no_certificate_count": summary["open_no_certificate_count"],
            "resource_metrics": pending_metrics,
            "bindings": {
                "frozen_manifest": ref(MANIFEST),
                "v2_generator": ref(RUNNER),
                "v2_backend": ref(BACKEND),
                "summary": ref(folder / "summary.json"),
                "outcomes": ref(folder / "outcomes.jsonl.gz"),
                "chunk_index": ref(folder / "backend-v2/index.json"),
            },
        }
        write_immutable(folder / "backend-v2/pipeline-generation-receipt.json", generation_receipt)

        audit_process = start(
            [sys.executable, str(CHECKER), "--segment", str(current)],
            folder / "backend-v2/audit-time.txt",
        )
        next_process = None
        if current < args.stop:
            next_number = current + 1
            next_folder = SEGMENTS / f"shallow-weighted-scale-{next_number:03d}"
            next_process = start(
                [sys.executable, str(RUNNER), "run", "--segment", str(next_number), "--workers", str(args.formula_workers)],
                next_folder / "backend-v2/generation-time.txt",
            )

        audit_metrics = audit_process.wait()
        audit = validate_audit(current, folder, summary)
        audit_receipt = {
            "schema_version": 1,
            "status": "VALID_PIPELINE_SEGMENT_PENDING_CENTRAL_IMPORT",
            "worker_id": args.worker_id,
            "segment_number": current,
            "producer_audit_status": audit["status"],
            "resource_metrics": audit_metrics,
            "maximum_unaudited_successor_segments": 1 if next_process else 0,
            "bindings": {
                "generation_receipt": ref(folder / "backend-v2/pipeline-generation-receipt.json"),
                "unchanged_checker": ref(CHECKER),
                "independent_audit": ref(folder / "independent-audit.json"),
            },
        }
        write_immutable(folder / "backend-v2/pipeline-audit-receipt.json", audit_receipt)
        execution = {
            "schema_version": 1,
            "status": "VALID_V2_SEGMENT_PENDING_CENTRAL_IMPORT",
            "worker_id": args.worker_id,
            "owned_range": [owner["first_segment"], owner["last_segment"]],
            "segment_number": current,
            "segment_id": folder.name,
            "formula_count": summary["selected"],
            "weighted_certificate_count": summary["weighted_certificate_count"],
            "open_no_certificate_count": summary["open_no_certificate_count"],
            "v2_worker_processes": args.formula_workers,
            "wall_seconds_including_generation_and_independent_audit": (
                pending_metrics["wall_seconds"] + audit_metrics["wall_seconds"]
            ),
            "pipeline_overlap_enabled": next_process is not None,
            "bindings": {
                "assignment_ledger": ref(ASSIGNMENT),
                "frozen_manifest": ref(MANIFEST),
                "backend_upgrade_audit": ref(UPGRADE),
                "v2_generator": ref(RUNNER),
                "v2_backend": ref(BACKEND),
                "unchanged_checker": ref(CHECKER),
                "summary": ref(folder / "summary.json"),
                "independent_audit": ref(folder / "independent-audit.json"),
                "outcome_archive": ref(folder / "outcomes.jsonl.gz"),
                "v2_chunk_index": ref(folder / "backend-v2/index.json"),
                "pipeline_generation_receipt": ref(folder / "backend-v2/pipeline-generation-receipt.json"),
                "pipeline_audit_receipt": ref(folder / "backend-v2/pipeline-audit-receipt.json"),
            },
        }
        write_immutable(folder / "backend-v2/execution-receipt.json", execution)
        subprocess.run(["git", "add", str(folder.relative_to(ROOT))], cwd=ROOT, check=True)
        subprocess.run(
            ["git", "commit", "-m", f"Record {args.worker_id} pipelined v2 segment {current:03d}"],
            cwd=ROOT,
            check=True,
        )
        subprocess.run(["git", "push", "origin", f"HEAD:{args.branch}"], cwd=ROOT, check=True)
        print(json.dumps({
            "segment": current,
            "certified": summary["weighted_certificate_count"],
            "gaps": summary["open_no_certificate_count"],
            "generation": pending_metrics,
            "audit": audit_metrics,
            "one_segment_backlog_bound_held": True,
        }, sort_keys=True), flush=True)
        if next_process is None:
            break
        pending_metrics = next_process.wait()
        current += 1


if __name__ == "__main__":
    main()

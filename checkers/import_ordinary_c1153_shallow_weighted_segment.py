#!/usr/bin/env python3
"""Verify and record one heterogeneous shallow-scale segment import.

The producing host's audit is not trusted transitively.  This importer reruns
the unchanged exact checker, verifies immutable ownership and source-commit
bindings, and additionally checks the v2 chunk partition when present.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "artifacts/classification/ordinary-c1153-v1/open-fifth-deficit-partition-v2/second-live-triple-gate-v1/shallow-weighted-scale-v1"
MANIFEST = BASE / "manifest.json"
ASSIGNMENT = BASE / "hybrid-execution-v1/assignment-ledger.json"
SEGMENTS = BASE / "segments"
OUT = BASE / "central-import-v1/segments"
V1 = ROOT / "scripts/run_ordinary_c1153_shallow_weighted_scale.py"
V2 = ROOT / "scripts/run_ordinary_c1153_shallow_weighted_scale_v2.py"
CHECKER = ROOT / "checkers/audit_ordinary_c1153_shallow_weighted_scale.py"

EXPECTED_MANIFEST = "bb06b660377ad6cc8132c41132867602366210b918f940d12fb156bac078c3f4"
EXPECTED_ASSIGNMENT = "63b4456c59f9c6690bdfa10c5940acefb56786d591c1c525c1e2607722ca6b83"
EXPECTED_V1 = "8165521d5440cc108335a10b380d53882478edd3d6bd19fdbd23488413c28920"
EXPECTED_V2 = "ec3492d733e4f1a9f10dbad634338a738e768128d7f9ba654a2256388429bb8d"
EXPECTED_CHECKER = "161319de67fcae2c430101b70086d61af512046166d7a379abeff6e18ba2a68a"

sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "checkers")]
from audit_ordinary_c1153_shallow_weighted_scale import audit  # noqa: E402
from run_ordinary_c1153_shallow_weighted_scale import object_sha, open_jobs  # noqa: E402


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sha_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def ref(path: Path) -> dict[str, str]:
    return {"path": str(path.relative_to(ROOT)), "sha256": sha(path)}


def check_ref(value: dict[str, str]) -> Path:
    path = ROOT / value["path"]
    if not path.is_file() or sha(path) != value["sha256"]:
        raise ValueError(f"bad imported artifact binding: {value}")
    return path


def git_bytes(commit: str, path: Path) -> bytes:
    relative = str(path.relative_to(ROOT))
    return subprocess.check_output(["git", "show", f"{commit}:{relative}"], cwd=ROOT)


def git_contains(branch: str, commit: str) -> None:
    subprocess.run(
        ["git", "merge-base", "--is-ancestor", commit, f"origin/{branch}"],
        cwd=ROOT,
        check=True,
    )


def resolve_owner(assignment: dict[str, object], segment: int) -> dict[str, str]:
    """Resolve both frozen ranges and the three pre-split completed segments."""
    for row in assignment["assignments"]:
        if row["first_segment"] <= segment <= row["last_segment"]:
            return {
                "branch": row["branch"],
                "worker_id": row["worker_id"],
            }
    for row in assignment["completed_before_split"]:
        if segment in row["segments"]:
            # These immutable commits predate the range branches.  They are
            # already ancestors of canonical origin/main, which is therefore
            # the source-commit containment boundary for central import.
            return {
                "branch": "main",
                "worker_id": row["host"],
            }
    raise ValueError(f"segment {segment:03d} has no frozen assignment owner")


def write(path: Path, value: object) -> None:
    raw = (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != raw:
            raise ValueError(f"refusing incompatible central import receipt: {path}")
        return
    temporary = path.with_suffix(".tmp")
    temporary.write_bytes(raw)
    os.replace(temporary, path)


def load_or_run_audit(segment: int, evidence: str | None) -> tuple[dict[str, object], dict[str, object]]:
    """Return an exact checker report and preserve how it was obtained.

    ``--audit-evidence`` is only for a checker invocation already completed in
    this canonical worktree.  The report is copied into the immutable import
    namespace and subjected to all of the same scalar/hash consistency checks
    below.  This avoids repeating an expensive block-by-block checker run
    solely because receipt generation was added after that run completed.
    """
    if evidence is None:
        return audit(segment), {"mode": "INLINE_EXACT_CHECKER_RUN"}
    source = Path(evidence).resolve()
    if not source.is_file():
        raise ValueError(f"central audit evidence is absent: {source}")
    report = json.loads(source.read_text())
    evidence_path = OUT.parent / "audit-evidence" / f"shallow-weighted-scale-{segment:03d}.json"
    write(evidence_path, report)
    return report, {
        "mode": "PRESERVED_PRIOR_EXACT_CHECKER_RUN",
        "report": ref(evidence_path),
    }


def verify_v2_chunks(folder: Path, expected_ids: list[str]) -> dict[str, object]:
    execution_path = folder / "backend-v2/execution-receipt.json"
    execution = json.loads(execution_path.read_text())
    for binding in execution["bindings"].values():
        check_ref(binding)
    index_path = folder / "backend-v2/index.json"
    index = json.loads(index_path.read_text())
    merged_rows: list[dict[str, object]] = []
    seen_chunks: set[int] = set()
    for row in index["chunks"]:
        chunk_index = row["chunk_index"]
        if chunk_index in seen_chunks:
            raise ValueError("duplicate v2 chunk index")
        seen_chunks.add(chunk_index)
        receipt_path = check_ref(row["receipt"])
        receipt = json.loads(receipt_path.read_text())
        archive_path = check_ref(row["archive"])
        chunk_rows = [
            json.loads(line)
            for line in gzip.decompress(archive_path.read_bytes()).splitlines()
        ]
        chunk_ids = [item["case_id"] for item in chunk_rows]
        if (
            receipt["chunk_index"] != chunk_index
            or receipt["case_count"] != len(chunk_rows)
            or receipt["case_ids_sha256"] != object_sha(chunk_ids)
            or receipt["archive"]["sha256"] != sha(archive_path)
        ):
            raise ValueError("v2 chunk receipt mismatch")
        merged_rows.extend(chunk_rows)
    merged_ids = [row["case_id"] for row in merged_rows]
    if merged_ids != expected_ids or index["case_ids_sha256"] != object_sha(expected_ids):
        raise ValueError("v2 chunks do not exactly partition the frozen segment")
    archive_rows = [
        json.loads(line)
        for line in gzip.decompress((folder / "outcomes.jsonl.gz").read_bytes()).splitlines()
    ]
    if archive_rows != merged_rows:
        raise ValueError("v2 deterministic merge differs from immutable chunks")
    return {
        "chunk_count": len(seen_chunks),
        "chunk_formula_coverage": len(merged_rows),
        "chunk_partition_exact": True,
        "execution_receipt": ref(execution_path),
        "chunk_index": ref(index_path),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--segment", type=int, required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument(
        "--audit-evidence",
        help="JSON stdout from a prior exact checker run in this canonical worktree",
    )
    args = parser.parse_args()

    if sha(MANIFEST) != EXPECTED_MANIFEST or sha(ASSIGNMENT) != EXPECTED_ASSIGNMENT:
        raise ValueError("canonical manifest or assignment ledger changed")
    if sha(V1) != EXPECTED_V1 or sha(V2) != EXPECTED_V2 or sha(CHECKER) != EXPECTED_CHECKER:
        raise ValueError("canonical generator/checker revision changed")
    manifest = json.loads(MANIFEST.read_text())
    segment = manifest["segments"][args.segment]
    folder = SEGMENTS / segment["segment_id"]
    if not folder.is_dir():
        raise ValueError("imported segment folder is absent")
    rows = open_jobs()[segment["start"] : segment["stop"]]
    expected_ids = [row["case_id"] for row in rows]
    if object_sha(expected_ids) != segment["case_ids_sha256"]:
        raise ValueError("frozen segment membership mismatch")

    assignment = json.loads(ASSIGNMENT.read_text())
    owner = resolve_owner(assignment, args.segment)
    git_contains(owner["branch"], args.source_commit)
    for path in (folder / "summary.json", folder / "independent-audit.json", folder / "outcomes.jsonl.gz"):
        if sha_bytes(git_bytes(args.source_commit, path)) != sha(path):
            raise ValueError(f"source commit does not contain imported bytes: {path}")

    v2_execution = folder / "backend-v2/execution-receipt.json"
    generator = V2 if v2_execution.exists() else V1
    expected_generator = EXPECTED_V2 if v2_execution.exists() else EXPECTED_V1
    if sha_bytes(git_bytes(args.source_commit, generator)) != expected_generator:
        raise ValueError("source commit generator revision mismatch")
    if sha_bytes(git_bytes(args.source_commit, CHECKER)) != EXPECTED_CHECKER:
        raise ValueError("source commit checker revision mismatch")

    # This reconstructs every exact residual domain and checks every retained
    # certificate against every eligible block.
    audit_report, audit_execution = load_or_run_audit(
        args.segment, args.audit_evidence
    )
    if audit_report["status"] not in {"VALID", "VALID_GATE_FAILED"}:
        raise ValueError("central exact segment audit failed")
    summary_path = folder / "summary.json"
    summary = json.loads(summary_path.read_text())
    if (
        audit_report["summary_sha256"] != sha(summary_path)
        or audit_report["selected"] != len(expected_ids)
        or audit_report["independently_checked_weighted_formulas"]
        != summary["weighted_certificate_count"]
    ):
        raise ValueError("central audit/summary count mismatch")

    v2_details = verify_v2_chunks(folder, expected_ids) if v2_execution.exists() else None
    receipt = {
        "schema_version": 1,
        "status": "VALID_CENTRAL_IMPORT",
        "segment_id": segment["segment_id"],
        "segment_number": args.segment,
        "source_commit": args.source_commit,
        "source_branch": owner["branch"],
        "worker_id": owner["worker_id"],
        "generator_version": "v2" if v2_execution.exists() else "v1",
        "bindings": {
            "frozen_manifest": ref(MANIFEST),
            "assignment_ledger": ref(ASSIGNMENT),
            "generator": ref(generator),
            "unchanged_checker": ref(CHECKER),
            "summary": ref(summary_path),
            "independent_audit": ref(folder / "independent-audit.json"),
            "outcomes": ref(folder / "outcomes.jsonl.gz"),
        },
        "formula_membership_exact_and_unique": len(expected_ids),
        "residual_domains_independently_reconstructed": len(expected_ids),
        "weighted_certificates_independently_checked": audit_report[
            "independently_checked_weighted_formulas"
        ],
        "open_no_certificate": audit_report["open_no_certificate_count"],
        "central_audit_execution": audit_execution,
        "v2_chunk_verification": v2_details,
        "claim_limit": (
            "This imports exact terminal formula receipts only. Ancestor closure requires "
            "a separate complete child-by-child aggregation audit."
        ),
    }
    receipt_path = OUT / f"{segment['segment_id']}.json"
    write(receipt_path, receipt)
    print(json.dumps(receipt, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Build a compact, non-destructive package for weighted-cover certificates."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "artifacts/classification/ordinary-c1153-v1/open-fifth-deficit-partition-v2/second-live-triple-gate-v1"
GATE = BASE / "multi-deficit-propagation-gate-v1"
STRUCTURAL = GATE / "manifest.json"
WEIGHTED = GATE / "weighted-generalization-gate-v1"
PROTOCOL = WEIGHTED / "protocol.json"
SUMMARY = WEIGHTED / "summary.json"
SOURCE_AUDIT = WEIGHTED / "independent-audit.json"
ILP_PROTOCOL = GATE / "ilp-forced-gate-v1/protocol.json"
TARGET = WEIGHTED / "compact-package-v1"
CERTIFICATES = TARGET / "certificates"
RECEIPTS = TARGET / "receipts"
SOURCE_INDEX = TARGET / "source-index.json"
BUILD_SUMMARY = TARGET / "build-summary.json"
COMPACT_AUDIT = TARGET / "independent-audit.json"
SCALE_MANIFEST = TARGET / "scale-manifest.json"
SEGMENT_SIZE = 256


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sha_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def object_sha(value: object) -> str:
    return sha_bytes(json.dumps(value, sort_keys=True, separators=(",", ":")).encode())


def compact_json(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def write_immutable(path: Path, raw: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != raw:
            raise ValueError(f"refusing to replace incompatible immutable file: {path}")
        return
    path.write_bytes(raw)


def gzip_bytes(raw: bytes) -> bytes:
    from io import BytesIO

    buffer = BytesIO()
    with gzip.GzipFile(filename="", mode="wb", fileobj=buffer, mtime=0, compresslevel=9) as stream:
        stream.write(raw)
    return buffer.getvalue()


def build_compact() -> dict[str, object]:
    protocol = json.loads(PROTOCOL.read_text())
    summary = json.loads(SUMMARY.read_text())
    audit = json.loads(SOURCE_AUDIT.read_text())
    if audit["status"] != "VALID" or audit["independently_checked_weighted_obstructions"] != 96:
        raise ValueError("source weighted audit is not a complete 96-case validation")
    if audit["protocol_sha256"] != sha(PROTOCOL) or audit["summary_sha256"] != sha(SUMMARY):
        raise ValueError("source audit bindings failed")
    if summary["completed"] != 96 or summary["weighted_certificate_count"] != 96:
        raise ValueError("source weighted gate is incomplete")
    outcomes = {row["case_id"]: row for row in summary["outcomes"]}
    if set(outcomes) != {row["case_id"] for row in protocol["cases"]}:
        raise ValueError("source weighted membership mismatch")
    rows = []
    for case_id in sorted(outcomes):
        result = outcomes[case_id]
        result_path = WEIGHTED / "results" / case_id / "result.json"
        if json.loads(result_path.read_text()) != result:
            raise ValueError(f"{case_id}: summary/result mismatch")
        certificate_reference = result["weighted_certificate"]
        if certificate_reference is None:
            raise ValueError(f"{case_id}: missing source certificate")
        certificate_path = ROOT / certificate_reference["path"]
        certificate_raw = certificate_path.read_bytes()
        if sha_bytes(certificate_raw) != certificate_reference["sha256"]:
            raise ValueError(f"{case_id}: source certificate hash mismatch")
        compact_path = CERTIFICATES / f"{case_id}.json.gz"
        write_immutable(compact_path, gzip_bytes(certificate_raw))
        rows.append({
            "case_id": case_id,
            "source_result": {
                "path": str(result_path.relative_to(ROOT)),
                "sha256": sha(result_path),
            },
            "source_certificate": {
                "path": str(certificate_path.relative_to(ROOT)),
                "sha256": sha_bytes(certificate_raw),
                "bytes": len(certificate_raw),
            },
            "compact_certificate": {
                "path": str(compact_path.relative_to(ROOT)),
                "sha256": sha(compact_path),
                "bytes": compact_path.stat().st_size,
                "uncompressed_sha256": sha_bytes(certificate_raw),
                "uncompressed_bytes": len(certificate_raw),
            },
        })
    write_immutable(SOURCE_INDEX, compact_json({
        "schema_version": 1,
        "status": "BUILT_PENDING_INDEPENDENT_AUDIT",
        "source_protocol_sha256": sha(PROTOCOL),
        "source_summary_sha256": sha(SUMMARY),
        "source_audit_sha256": sha(SOURCE_AUDIT),
        "case_count": len(rows),
        "case_ids_sha256": object_sha([row["case_id"] for row in rows]),
        "cases": rows,
        "claim_limit": "Compression only. No mathematical claim follows without independent decompression, source binding, domain reconstruction, and arithmetic checking.",
    }))
    certificate_bytes = sum((ROOT / row["compact_certificate"]["path"]).stat().st_size for row in rows)
    report = {
        "schema_version": 1,
        "status": "BUILT_PENDING_INDEPENDENT_AUDIT",
        "bindings": {
            "source_protocol_sha256": sha(PROTOCOL),
            "source_summary_sha256": sha(SUMMARY),
            "source_audit_sha256": sha(SOURCE_AUDIT),
            "source_index_sha256": sha(SOURCE_INDEX),
        },
        "case_count": 96,
        "compact_certificate_bytes": certificate_bytes,
        "source_index_bytes": SOURCE_INDEX.stat().st_size,
        "original_certificate_bytes": sum(row["source_certificate"]["bytes"] for row in rows),
        "original_artifacts_preserved": True,
        "new_mathematical_compute": False,
    }
    write_immutable(BUILD_SUMMARY, compact_json(report))
    return report


def make_case_id(formula_id: str, path: list[int]) -> str:
    return f"{formula_id}-cube-{path[0]:03d}-{path[1]:03d}"


def freeze_scale() -> dict[str, object]:
    compact_audit = json.loads(COMPACT_AUDIT.read_text())
    if compact_audit["status"] != "VALID" or not compact_audit["success_gate_passed"]:
        raise ValueError("compact storage gate did not pass")
    structural = json.loads(STRUCTURAL.read_text())
    weighted = json.loads(PROTOCOL.read_text())
    ilp = json.loads(ILP_PROTOCOL.read_text())
    all_cases = []
    for formula in structural["formulas"]:
        for terminal in formula["terminal_partition"]:
            if terminal["kind"] != "frontier":
                continue
            path = terminal["path"]
            all_cases.append({
                "branch_count_quantile": formula["branch_count_quantile"],
                "case_id": make_case_id(formula["leaf_id"], path),
                "cube_path": path,
                "formula_id": formula["leaf_id"],
                "rank_band": formula["rank_band"],
                "root_class": formula["root_class"],
                "sample_category": formula["sample_category"],
                "second_index": formula["second_index"],
                "stabilizer_tier": formula["stabilizer_tier"],
                "target_child_id": formula["target_child_id"],
            })
    all_cases.sort(key=lambda row: row["case_id"])
    if len(all_cases) != 4402 or len({row["case_id"] for row in all_cases}) != 4402:
        raise ValueError("structural frontier is not exactly 4,402 unique cubes")
    closed = {row["case_id"] for row in weighted["cases"]} | {row["case_id"] for row in ilp["cases"]}
    remaining = [row for row in all_cases if row["case_id"] not in closed]
    if len(closed) != 102 or len(remaining) != 4300:
        raise ValueError("scale manifest is not exactly 4,300 open cubes")
    segments = []
    for start in range(0, len(remaining), SEGMENT_SIZE):
        cases = remaining[start:start + SEGMENT_SIZE]
        segments.append({
            "segment_id": f"weighted-scale-{start // SEGMENT_SIZE:03d}",
            "start_index": start,
            "case_count": len(cases),
            "case_ids_sha256": object_sha([row["case_id"] for row in cases]),
            "cases": cases,
        })
    manifest = {
        "schema_version": 1,
        "status": "FROZEN_NOT_RUN",
        "bindings": {
            "structural_manifest_sha256": sha(STRUCTURAL),
            "weighted_protocol_sha256": sha(PROTOCOL),
            "ilp_protocol_sha256": sha(ILP_PROTOCOL),
            "compact_audit_sha256": sha(COMPACT_AUDIT),
        },
        "frontier_case_count": 4402,
        "certified_weighted_case_count": 102,
        "open_case_count": 4300,
        "open_case_ids_sha256": object_sha([row["case_id"] for row in remaining]),
        "segment_size": SEGMENT_SIZE,
        "segment_count": len(segments),
        "segments": segments,
        "fixed_route": {
            "continuous_lp_seconds_per_case": 1,
            "parallelism": 1,
            "certificate": "Exact downward-rounded nonnegative integer triple weights.",
            "artifact_format": "compact-package-v1 deterministic gzip certificate plus hash-bound compact receipt and pointer-only aggregate index",
        },
        "assignment": {
            "cloud": {"role": "EXCLUSIVE_LP_AND_RECEIPT_OWNER", "segment_ids": [row["segment_id"] for row in segments]},
            "local": {"role": "INDEPENDENT_CHECK_AND_PUBLICATION_ONLY", "segment_ids": []},
        },
        "execution_gate": "Frozen only. A later reviewed instruction must authorize any segment execution.",
        "claim_limit": "No open cube is closed by this manifest. Each future certificate requires independent exact checking; ancestors require complete aggregation.",
    }
    write_immutable(SCALE_MANIFEST, compact_json(manifest))
    return {
        "status": manifest["status"],
        "open_case_count": manifest["open_case_count"],
        "segment_count": manifest["segment_count"],
        "scale_manifest_sha256": sha(SCALE_MANIFEST),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("compact", "freeze-scale"))
    args = parser.parse_args()
    report = build_compact() if args.mode == "compact" else freeze_scale()
    print(json.dumps(report, indent=2, sort_keys=True))

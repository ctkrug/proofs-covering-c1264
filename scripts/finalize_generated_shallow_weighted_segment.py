#!/usr/bin/env python3
"""Finalize an already-generated and independently audited pipeline segment.

This recovery path never invokes either the generator or the checker.  It is
for an immutable segment stranded after an orchestration failure, and records
the missing live resource-monitor fields honestly instead of fabricating them.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
from pathlib import Path

import run_ordinary_c1153_shallow_weighted_pipeline_v2 as pipeline


ROOT = pipeline.ROOT


def write_recovered_time(source: Path, target: Path) -> None:
    raw = source.read_bytes()
    if not raw.startswith(b"real ") or b"maximum resident set size" not in raw:
        raise ValueError("recovered generation timing is not recognizable /usr/bin/time output")
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        if target.read_bytes() != raw:
            raise ValueError("refusing incompatible recovered timing artifact")
        return
    temporary = target.with_suffix(".tmp")
    temporary.write_bytes(raw)
    os.replace(temporary, target)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--segment", type=int, required=True)
    parser.add_argument("--worker-id", required=True)
    parser.add_argument("--branch", required=True)
    parser.add_argument("--recovered-generation-time", type=Path, required=True)
    args = parser.parse_args()

    for path, expected in pipeline.EXPECTED.items():
        if pipeline.sha(path) != expected:
            raise ValueError(f"pinned pipeline input changed: {path}")
    assignment = json.loads(pipeline.ASSIGNMENT.read_text())
    owner = next(row for row in assignment["assignments"] if row["worker_id"] == args.worker_id)
    if (
        owner["branch"] != args.branch
        or not owner["first_segment"] <= args.segment <= owner["last_segment"]
    ):
        raise ValueError("recovery violates immutable ownership")

    folder, summary = pipeline.validate_generation(args.segment)
    audit = pipeline.validate_audit(args.segment, folder, summary)
    backend = folder / "backend-v2"
    recovered_time = backend / "generation-time-recovered.txt"
    write_recovered_time(args.recovered_generation_time, recovered_time)

    incident = {
        "schema_version": 1,
        "status": "PRESERVED_ORCHESTRATION_INCIDENT",
        "worker_id": args.worker_id,
        "segment_number": args.segment,
        "mathematical_artifacts_affected": False,
        "facts": [
            "The predecessor segment was independently audited before its Git push failed.",
            "The producer had already generated this immutable successor segment.",
            "The exact successor independent audit subsequently passed.",
            "The original pipeline assumed every segment contained 2048 formulas, but the frozen final segment contains 1800.",
            "No formula was regenerated and no certificate, outcome, summary, or audit was modified.",
        ],
        "resource_measurement_limit": (
            "The recovered /usr/bin/time record is preserved, but live process-tree, "
            "swap, and disk deltas were lost when the original pipeline exited."
        ),
        "bindings": {
            "summary": pipeline.ref(folder / "summary.json"),
            "independent_audit": pipeline.ref(folder / "independent-audit.json"),
            "recovered_generation_time": pipeline.ref(recovered_time),
        },
    }
    incident_path = backend / "recovery-incident.json"
    pipeline.write_immutable(incident_path, incident)

    unavailable_metrics = {
        "measurement_status": "PARTIALLY_RECOVERED_AFTER_ORCHESTRATION_EXIT",
        "recovered_time_output": pipeline.ref(recovered_time),
        "peak_process_tree_rss_bytes": None,
        "swap_used_before_bytes": None,
        "peak_swap_used_bytes": None,
        "disk_free_before_bytes": None,
        "disk_free_after_bytes": shutil.disk_usage(ROOT).free,
    }
    generation_receipt = {
        "schema_version": 1,
        "status": "PENDING_FULL_INDEPENDENT_AUDIT",
        "worker_id": args.worker_id,
        "segment_number": args.segment,
        "formula_count": summary["selected"],
        "weighted_certificate_count": summary["weighted_certificate_count"],
        "open_no_certificate_count": summary["open_no_certificate_count"],
        "resource_metrics": unavailable_metrics,
        "recovery_incident": pipeline.ref(incident_path),
        "bindings": {
            "frozen_manifest": pipeline.ref(pipeline.MANIFEST),
            "v2_generator": pipeline.ref(pipeline.RUNNER),
            "v2_backend": pipeline.ref(pipeline.BACKEND),
            "summary": pipeline.ref(folder / "summary.json"),
            "outcomes": pipeline.ref(folder / "outcomes.jsonl.gz"),
            "chunk_index": pipeline.ref(backend / "index.json"),
        },
    }
    generation_path = backend / "pipeline-generation-receipt.json"
    pipeline.write_immutable(generation_path, generation_receipt)

    audit_receipt = {
        "schema_version": 1,
        "status": "VALID_PIPELINE_SEGMENT_PENDING_CENTRAL_IMPORT",
        "worker_id": args.worker_id,
        "segment_number": args.segment,
        "producer_audit_status": audit["status"],
        "resource_metrics": {
            "measurement_status": "EXACT_AUDIT_COMPLETED_OUTSIDE_ORIGINAL_MONITOR",
            "independent_audit": pipeline.ref(folder / "independent-audit.json"),
        },
        "maximum_unaudited_successor_segments": 0,
        "recovery_incident": pipeline.ref(incident_path),
        "bindings": {
            "generation_receipt": pipeline.ref(generation_path),
            "unchanged_checker": pipeline.ref(pipeline.CHECKER),
            "independent_audit": pipeline.ref(folder / "independent-audit.json"),
        },
    }
    audit_path = backend / "pipeline-audit-receipt.json"
    pipeline.write_immutable(audit_path, audit_receipt)

    execution = {
        "schema_version": 1,
        "status": "VALID_V2_SEGMENT_PENDING_CENTRAL_IMPORT",
        "worker_id": args.worker_id,
        "owned_range": [owner["first_segment"], owner["last_segment"]],
        "segment_number": args.segment,
        "segment_id": folder.name,
        "formula_count": summary["selected"],
        "weighted_certificate_count": summary["weighted_certificate_count"],
        "open_no_certificate_count": summary["open_no_certificate_count"],
        "v2_worker_processes": 1,
        "wall_seconds_including_generation_and_independent_audit": None,
        "pipeline_overlap_enabled": False,
        "recovery_incident": pipeline.ref(incident_path),
        "bindings": {
            "assignment_ledger": pipeline.ref(pipeline.ASSIGNMENT),
            "frozen_manifest": pipeline.ref(pipeline.MANIFEST),
            "backend_upgrade_audit": pipeline.ref(pipeline.UPGRADE),
            "v2_generator": pipeline.ref(pipeline.RUNNER),
            "v2_backend": pipeline.ref(pipeline.BACKEND),
            "unchanged_checker": pipeline.ref(pipeline.CHECKER),
            "summary": pipeline.ref(folder / "summary.json"),
            "independent_audit": pipeline.ref(folder / "independent-audit.json"),
            "outcome_archive": pipeline.ref(folder / "outcomes.jsonl.gz"),
            "v2_chunk_index": pipeline.ref(backend / "index.json"),
            "pipeline_generation_receipt": pipeline.ref(generation_path),
            "pipeline_audit_receipt": pipeline.ref(audit_path),
            "recovery_incident": pipeline.ref(incident_path),
        },
    }
    pipeline.write_immutable(backend / "execution-receipt.json", execution)
    print(json.dumps({
        "status": "VALID_RECOVERED_SEGMENT_PENDING_CENTRAL_IMPORT",
        "segment": args.segment,
        "selected": summary["selected"],
        "weighted_certificates": summary["weighted_certificate_count"],
        "open_no_certificate": summary["open_no_certificate_count"],
        "audit": audit["status"],
    }, sort_keys=True))


if __name__ == "__main__":
    main()

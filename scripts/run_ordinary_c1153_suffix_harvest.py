#!/usr/bin/env python3
"""Bounded self-advancing suffix harvest with sampled QA gates."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "artifacts/classification/ordinary-c1153-v1/hard-tail-fifth-split"
PYTHON = ROOT / ".venv/bin/python"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def update_ledger() -> dict[str, object]:
    route = json.loads((BASE / "suffix-scale-manifest.json").read_text())
    segments = []
    totals = {"selected": 0, "completed": 0, "provisional_solver_unsat": 0, "certified_independent_replay": 0,
              "fixed_cap_timeout": 0, "sat": 0, "compressed_proof_bytes": 0}
    for segment_dir in sorted((BASE / "segments").glob("segment-*")):
        receipt_path, audit_path = segment_dir / "runner-receipt.json", segment_dir / "independent-audit.json"
        if not receipt_path.exists() or not audit_path.exists():
            continue
        receipt, audit = json.loads(receipt_path.read_text()), json.loads(audit_path.read_text())
        provisional = sum(value for key, value in receipt["counts"].items() if key in ("UNSAT_VERIFIED_BY_RUNNER", "PROVISIONAL_UNSAT_PROOF_RETAINED"))
        certified = audit["counts"]["INDEPENDENT_SAMPLE_UNSAT_REPLAYED"]
        timeout = receipt["counts"].get("FIXED_CAP_TIMEOUT", 0)
        sat = sum(value for key, value in receipt["counts"].items() if key.startswith("SAT_"))
        row = {"segment": receipt["segment"], "selected": receipt["selected"], "completed": receipt["completed"],
               "provisional_solver_unsat": provisional, "certified_independent_replay": certified,
               "fixed_cap_timeout": timeout, "sat": sat, "compressed_proof_bytes": receipt["compressed_proof_bytes"],
               "runner_receipt_sha256": sha(receipt_path), "independent_audit_sha256": sha(audit_path),
               "qa_passed": audit["continuation_gate_passed"]}
        segments.append(row)
        for key in totals:
            totals[key] += row[key]
    ledger = {
        "schema_version": 1, "status": "CURRENT",
        "route_manifest_sha256": sha(BASE / "suffix-scale-manifest.json"), "segments": segments, "totals": totals,
        "remaining_unmeasured_scale_jobs": route["accounting"]["pending_scale_workload"] - totals["completed"],
        "complete_fourth_parents_closed": 0,
        "ledger_definitions": {
            "provisional_harvest": "Solver UNSAT with immutable exact-CNF/proof receipts; planning only, never a theorem closure.",
            "certified": "Certificate received a separate exact-CNF reconstruction and external replay; final classification still requires exhaustive aggregate replay.",
        },
        "claim_limit": "No fourth parent or ordinary classification branch closes from partial fifth-child harvesting.",
    }
    target = BASE / "suffix-scale-ledger.json"
    target.write_text(json.dumps(ledger, indent=2, sort_keys=True) + "\n")
    return ledger


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", type=int, required=True)
    parser.add_argument("--stop", type=int, required=True, help="Inclusive last segment")
    args = parser.parse_args()
    events = []
    started = time.monotonic()
    for number in range(args.start, args.stop + 1):
        if shutil.disk_usage(ROOT).free < 9 * 1024**3:
            events.append({"segment": number, "status": "STOPPED_LOW_DISK"})
            break
        run = subprocess.run([str(PYTHON), str(ROOT / "scripts/run_ordinary_c1153_fifth_suffix_segment.py"), "--segment", str(number)])
        if run.returncode != 0:
            events.append({"segment": number, "status": "STOPPED_RUNNER_FAILURE", "returncode": run.returncode})
            break
        audit = subprocess.run([str(PYTHON), str(ROOT / "checkers/verify_ordinary_c1153_fifth_suffix_segment.py"), "--segment", str(number), "--sample-size", "32"])
        audit_path = BASE / "segments" / f"segment-{number:04d}" / "independent-audit.json"
        if audit.returncode != 0 or not audit_path.exists():
            events.append({"segment": number, "status": "STOPPED_AUDIT_FAILURE", "returncode": audit.returncode})
            break
        report = json.loads(audit_path.read_text())
        events.append({"segment": number, "status": "QA_PASSED" if report["continuation_gate_passed"] else "STOPPED_QA_GATE",
                       "audit_sha256": sha(audit_path), "counts": report["counts"]})
        update_ledger()
        if not report["continuation_gate_passed"] or report["counts"]["SAT_VALIDATED"]:
            break
    ledger = update_ledger()
    controller = {"schema_version": 1, "requested_start": args.start, "requested_stop": args.stop,
                  "events": events, "wall_seconds": time.monotonic() - started,
                  "ledger_sha256": sha(BASE / "suffix-scale-ledger.json"), "totals": ledger["totals"],
                  "status": "COMPLETE" if events and events[-1]["segment"] == args.stop and events[-1]["status"] == "QA_PASSED" else "STOPPED"}
    target = BASE / f"controller-{args.start:04d}-{args.stop:04d}.json"
    target.write_text(json.dumps(controller, indent=2, sort_keys=True) + "\n")
    print(json.dumps(controller, indent=2, sort_keys=True))
    sys.exit(0 if controller["status"] == "COMPLETE" else 1)


if __name__ == "__main__":
    main()

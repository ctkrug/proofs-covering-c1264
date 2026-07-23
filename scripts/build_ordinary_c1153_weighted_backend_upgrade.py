#!/usr/bin/env python3
"""Build the immutable backend-v2 activation receipt."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "artifacts/classification/ordinary-c1153-v1/open-fifth-deficit-partition-v2/second-live-triple-gate-v1/shallow-weighted-scale-v1"
OUT = BASE / "backend-upgrade-v1"
MANIFEST = BASE / "manifest.json"
PERF = BASE / "performance-engineering-v1"
SUMMARY = PERF / "benchmark-summary.json"
PERF_AUDIT = PERF / "optimized-workers-4/independent-audit.json"
REFERENCE = BASE / "segments/shallow-weighted-scale-002/outcomes.jsonl.gz"
BACKEND = ROOT / "scripts/ordinary_c1153_weighted_backend_v2.py"
GENERATOR = ROOT / "scripts/run_ordinary_c1153_shallow_weighted_scale_v2.py"
CHECKER = ROOT / "checkers/audit_ordinary_c1153_shallow_weighted_scale.py"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def ref(path: Path) -> dict[str, str]:
    return {"path": str(path.relative_to(ROOT)), "sha256": sha(path)}


def write(path: Path, value: object) -> None:
    raw = (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != raw:
            raise ValueError(f"refusing incompatible upgrade receipt: {path}")
        return
    temporary = path.with_suffix(".tmp")
    temporary.write_bytes(raw)
    os.replace(temporary, path)


def main() -> None:
    summary = json.loads(SUMMARY.read_text())
    audit = json.loads(PERF_AUDIT.read_text())
    if summary["status"] != "VALID_PERFORMANCE_GATE_COMPLETE":
        raise ValueError("v2 performance gate did not pass")
    selected = summary["selected_backend"]
    if (
        selected["formula_coverage_agreement"] != "2048/2048"
        or selected["residual_domain_hash_agreement"] != "2048/2048"
        or selected["terminal_nonterminal_verdict_agreement"] != "2048/2048"
        or selected["exact_checker_acceptance"] != "2043/2043 terminal formulas"
    ):
        raise ValueError("v2 benchmark equivalence is incomplete")
    if (
        audit["status"] != "VALID"
        or audit["selected"] != 2048
        or audit["independently_checked_exact_certificates"] != 2043
        or audit["open_reference_gaps"] != 5
    ):
        raise ValueError("v2 independent benchmark audit is incomplete")
    receipt = {
        "schema_version": 1,
        "status": "BUILT_PENDING_INDEPENDENT_AUDIT",
        "frozen_shallow_scale_manifest": ref(MANIFEST),
        "v2_generator": ref(GENERATOR),
        "v2_backend": ref(BACKEND),
        "unchanged_independent_segment_checker": ref(CHECKER),
        "benchmark_evidence": {
            "input_reference_archive": ref(REFERENCE),
            "benchmark_summary": ref(SUMMARY),
            "independent_equivalence_audit": ref(PERF_AUDIT),
            "formula_count": 2048,
            "residual_domain_hash_agreement": 2048,
            "terminal_verdict_agreement": 2048,
            "independently_accepted_certificates": 2043,
            "honest_open_gaps": 5,
        },
        "heterogeneous_generator_rule": (
            "V1 and V2 generator receipts may coexist only when each formula is bound "
            "to its exact source CNF and reconstructed residual-domain hashes, its segment "
            "membership is exact and unique, and every claimed weighted certificate passes "
            "the unchanged independent block-by-block checker. Generator identity never "
            "authorizes certificate reuse, formula identification, or ancestor closure."
        ),
        "activation_scope": (
            "Only previously unstarted segments at safe immutable segment boundaries inside "
            "the existing exclusive cloud-a, local-a, and local-b ranges."
        ),
        "past_artifact_effect": "NONE; every v1 receipt remains byte-identical and authoritative.",
        "mathematical_ledger_effect": "NONE; this is execution-backend compatibility only.",
    }
    write(OUT / "receipt.json", receipt)
    print(json.dumps(receipt, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

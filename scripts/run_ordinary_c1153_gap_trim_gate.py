#!/usr/bin/env python3
"""Run the frozen 512-case read-only shallow-gap eliminator gate."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import multiprocessing
import os
import statistics
import sys
import time
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "checkers")]

from audit_ordinary_c1153_fourth_inventory import reconstruct_hierarchy  # noqa: E402
from audit_ordinary_c1153_ilp_forced_gate import residual_domain  # noqa: E402
from audit_ordinary_c1153_shallow_weighted_scale import all_open_jobs  # noqa: E402
from ordinary_c1153_gap_trim import (  # noqa: E402
    BLOCK_TRIPLES,
    compact,
    dominance_reduce,
    exact_domain_sha,
    object_sha,
    propagate_exact,
    state_domain,
    weighted_proposal,
)


BASE = (
    ROOT
    / "artifacts/classification/ordinary-c1153-v1/open-fifth-deficit-partition-v2/"
    "second-live-triple-gate-v1"
)
TARGET = Path(
    os.environ.get("C1264_GAP_TRIM_OUTPUT", BASE / "gap-trim-v1")
).resolve()
MANIFEST = TARGET / "manifest.json"
CORPUS = TARGET / "corpus.jsonl.gz"
PROTOCOL = TARGET / "gate-512-protocol.json"
RESULTS = TARGET / "gate-512-results.jsonl.gz"
SUMMARY = TARGET / "gate-512-summary.json"
LP_SECONDS = 1.0
MAX_TWO_LAYER_BRANCHES = 32
_JOBS: dict[str, dict[str, object]] = {}
_CASES: dict[str, dict[str, object]] = {}
_PARENTS: dict[str, bytes] = {}


def sha_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def freeze_protocol(workers: int) -> dict[str, object]:
    manifest_raw = MANIFEST.read_bytes()
    manifest = json.loads(manifest_raw)
    corpus_raw = CORPUS.read_bytes()
    if sha_bytes(corpus_raw) != manifest["corpus"]["sha256"]:
        raise ValueError("gap corpus hash mismatch")
    protocol = {
        "schema_version": 1,
        "status": "FROZEN_NOT_RUN",
        "corpus_manifest": {
            "path": str(MANIFEST),
            "sha256": sha_bytes(manifest_raw),
        },
        "corpus": {
            "path": str(CORPUS),
            "sha256": sha_bytes(corpus_raw),
        },
        "sample_size": manifest["sample_size"],
        "sample_case_ids": manifest["sample_case_ids"],
        "sample_case_ids_sha256": manifest["sample_case_ids_sha256"],
        "fixed_methods": [
            "exact zero/one-coverer and cardinality propagation",
            "coverage-row dominance with explicit subset witnesses",
            "post-propagation exact weighted obstruction",
            "complete first-occupied minimum-coverer split plus exact child propagation/weighting",
        ],
        "fixed_budget": {
            "continuous_lp_seconds_per_proposal": LP_SECONDS,
            "maximum_two_layer_children": MAX_TWO_LAYER_BRANCHES,
            "workers": workers,
        },
        "partition_rule": (
            "Choose the lexicographically first uncovered triple among those with the "
            "fewest eligible blocks. Child i forbids all earlier coverers and fixes "
            "coverer i, giving an exhaustive SAT-model-disjoint first-occupied split."
        ),
        "dominance_rule": (
            "A coverage row is dropped only when the eligible-coverer set of a retained "
            "row is a subset; satisfying the retained row logically implies the dropped row."
        ),
        "success_gate": (
            "Net-new exact formula contradictions at cheap median generation/check cost, "
            "or a complete sound partition isolating a materially smaller coherent residual."
        ),
        "stop_rule": (
            "Stop after exactly the frozen sample, or immediately on SAT candidate, "
            "source-domain mismatch, certificate/checker disagreement, or resource failure."
        ),
        "claim_limit": (
            "Formula-level only. No target child or ancestor closes without separate "
            "complete aggregation."
        ),
    }
    raw = json.dumps(protocol, indent=2, sort_keys=True) + "\n"
    if PROTOCOL.exists() and PROTOCOL.read_text() != raw:
        raise ValueError("refusing to replace incompatible frozen protocol")
    PROTOCOL.write_text(raw)
    return protocol


def load_inputs() -> tuple[list[dict[str, object]], dict[str, object]]:
    manifest = json.loads(MANIFEST.read_text())
    raw = gzip.decompress(CORPUS.read_bytes())
    rows = [json.loads(line) for line in raw.splitlines()]
    by_id = {row["case_id"]: row for row in rows}
    selected = [by_id[case_id] for case_id in manifest["sample_case_ids"]]
    if object_sha([row["case_id"] for row in selected]) != manifest["sample_case_ids_sha256"]:
        raise ValueError("sample membership mismatch")
    return selected, manifest


def initialize() -> None:
    global _JOBS, _CASES, _PARENTS
    _JOBS = {row["case_id"]: row for row in all_open_jobs()}
    source = json.loads((BASE / "manifest.json").read_text())
    _CASES = {row["id"]: row for row in source["target_cases"]}
    _, _PARENTS, _, _ = reconstruct_hierarchy()


def proposal_on_state(domain: dict[str, object]) -> tuple[dict[str, object] | None, dict[str, object], dict[str, object]]:
    uncovered = [tuple(row) for row in domain["uncovered"]]
    available = list(domain["available"])
    reduced, witnesses = dominance_reduce(uncovered, available)
    certificate, proposal = weighted_proposal(
        reduced, available, int(domain["remaining_slots"]), LP_SECONDS
    )
    dominance = {
        "original_row_count": len(uncovered),
        "retained_row_count": len(reduced),
        "retained_triples": [list(row) for row in reduced],
        "dropped_rows": witnesses,
        "preservation": (
            "Each dropped row has a retained witness whose eligible-coverer set is a "
            "subset, so the witness coverage inequality implies the dropped inequality."
        ),
    }
    return certificate, proposal, dominance


def solve_one(gap: dict[str, object]) -> dict[str, object]:
    started = time.perf_counter()
    case_id = gap["case_id"]
    job = _JOBS[case_id]
    case = _CASES[job["target_child_id"]]
    parent_id = Path(case["third_level_parent_cnf"]["path"]).parent.name
    domain = residual_domain(job, case, _PARENTS[parent_id])
    if exact_domain_sha(domain) != gap["exact_residual_domain_sha256"]:
        raise ValueError(f"{case_id}: source domain changed")
    status, fixed, forbidden, detail = propagate_exact(
        set(domain["fixed"]), set(domain["forbidden"])
    )
    result: dict[str, object] = {
        "case_id": case_id,
        "source_exact_residual_domain_sha256": gap["exact_residual_domain_sha256"],
        "source_audit_sha256": gap["source_audit_sha256"],
        "source_archive_sha256": gap["source_archive_sha256"],
        "initial_propagation": {
            "status": status,
            "fixed": sorted(fixed),
            "forbidden": sorted(forbidden),
            "detail": detail,
        },
        "terminal": False,
        "method": "OPEN",
    }
    if status.startswith("CONTRADICTION"):
        result.update(terminal=True, method="FORCED_PROPAGATION")
    elif status == "SAT_COVER":
        result.update(terminal=False, method="SAT_CANDIDATE", witness_variables=sorted(fixed))
    else:
        propagated = state_domain(fixed, forbidden, detail)
        result["propagated_domain_sha256"] = exact_domain_sha(propagated)
        certificate, proposal, dominance = proposal_on_state(propagated)
        result["dominance"] = dominance
        result["post_propagation_weighted"] = {
            "proposal": proposal,
            "certificate": certificate,
        }
        if certificate is not None:
            result.update(terminal=True, method="PROPAGATED_WEIGHTED")
        else:
            reduced = [tuple(row) for row in dominance["retained_triples"]]
            available = list(propagated["available"])
            coverers = {
                triple: [
                    value
                    for value in available
                    if triple in BLOCK_TRIPLES[value - 1]
                ]
                for triple in reduced
            }
            selected = min(reduced, key=lambda row: (len(coverers[row]), row))
            ordered_coverers = sorted(coverers[selected])
            partition: dict[str, object] = {
                "selected_triple": list(selected),
                "coverers": ordered_coverers,
                "child_count": len(ordered_coverers),
                "children": [],
                "complete": len(ordered_coverers) <= MAX_TWO_LAYER_BRANCHES,
            }
            if len(ordered_coverers) <= MAX_TWO_LAYER_BRANCHES:
                all_terminal = True
                earlier: set[int] = set()
                for index, variable in enumerate(ordered_coverers):
                    child_status, child_fixed, child_forbidden, child_detail = propagate_exact(
                        fixed | {variable}, forbidden | earlier
                    )
                    child: dict[str, object] = {
                        "index": index,
                        "fixed_variable": variable,
                        "earlier_forbidden": sorted(earlier),
                        "propagation": {
                            "status": child_status,
                            "fixed": sorted(child_fixed),
                            "forbidden": sorted(child_forbidden),
                            "detail": child_detail,
                        },
                        "terminal": child_status.startswith("CONTRADICTION"),
                    }
                    if child_status == "SAT_COVER":
                        child["method"] = "SAT_CANDIDATE"
                        child["witness_variables"] = sorted(child_fixed)
                        all_terminal = False
                    elif child_status.startswith("CONTRADICTION"):
                        child["method"] = "FORCED_PROPAGATION"
                    else:
                        child_domain = state_domain(child_fixed, child_forbidden, child_detail)
                        child["domain_sha256"] = exact_domain_sha(child_domain)
                        child_certificate, child_proposal, child_dominance = proposal_on_state(
                            child_domain
                        )
                        child["dominance"] = child_dominance
                        child["weighted"] = {
                            "proposal": child_proposal,
                            "certificate": child_certificate,
                        }
                        child["terminal"] = child_certificate is not None
                        child["method"] = (
                            "WEIGHTED" if child_certificate is not None else "OPEN"
                        )
                        all_terminal &= child["terminal"]
                    partition["children"].append(child)
                    earlier.add(variable)
                partition["all_children_terminal"] = all_terminal
                if all_terminal:
                    result.update(terminal=True, method="TWO_LAYER_WEIGHTED")
            result["two_layer_partition"] = partition
    result["generation_seconds"] = time.perf_counter() - started
    result["certificate_payload_bytes"] = len(compact(result))
    return result


def run(workers: int) -> dict[str, object]:
    protocol = freeze_protocol(workers)
    selected, manifest = load_inputs()
    initialize()
    if workers == 1:
        outcomes = [solve_one(row) for row in selected]
    else:
        context = multiprocessing.get_context("fork")
        with context.Pool(processes=workers, initializer=initialize) as pool:
            outcomes = pool.map(solve_one, selected)
    if [row["case_id"] for row in outcomes] != protocol["sample_case_ids"]:
        raise ValueError("result membership/order mismatch")
    sat = [row for row in outcomes if row["method"] == "SAT_CANDIDATE"]
    sat.extend(
        child
        for row in outcomes
        for child in row.get("two_layer_partition", {}).get("children", [])
        if child.get("method") == "SAT_CANDIDATE"
    )
    raw = b"".join(compact(row) + b"\n" for row in outcomes)
    compressed = gzip.compress(raw, compresslevel=9, mtime=0)
    RESULTS.write_bytes(compressed)
    counts = Counter(row["method"] for row in outcomes)
    by_stratum: dict[str, Counter[str]] = {}
    gap_by_id = {row["case_id"]: row for row in selected}
    for row in outcomes:
        gap = gap_by_id[row["case_id"]]
        key = "|".join(
            (
                gap["root_class"],
                gap["rank_band"],
                gap["branch_count_quantile"],
                gap["stabilizer_tier"],
            )
        )
        by_stratum.setdefault(key, Counter())[row["method"]] += 1
    summary = {
        "schema_version": 1,
        "status": "COMPLETE_PENDING_INDEPENDENT_AUDIT",
        "protocol_sha256": sha_bytes(PROTOCOL.read_bytes()),
        "corpus_manifest_sha256": sha_bytes(MANIFEST.read_bytes()),
        "sample_size": len(outcomes),
        "terminal_formula_count": sum(row["terminal"] for row in outcomes),
        "open_formula_count": sum(not row["terminal"] for row in outcomes),
        "sat_candidate_count": len(sat),
        "counts_by_method": dict(sorted(counts.items())),
        "counts_by_stratum": {
            key: dict(sorted(value.items())) for key, value in sorted(by_stratum.items())
        },
        "median_generation_seconds": statistics.median(
            row["generation_seconds"] for row in outcomes
        ),
        "maximum_generation_seconds": max(row["generation_seconds"] for row in outcomes),
        "median_certificate_payload_bytes": statistics.median(
            row["certificate_payload_bytes"] for row in outcomes
        ),
        "maximum_certificate_payload_bytes": max(
            row["certificate_payload_bytes"] for row in outcomes
        ),
        "results": {
            "path": str(RESULTS),
            "sha256": sha_bytes(compressed),
            "uncompressed_sha256": sha_bytes(raw),
            "bytes": len(compressed),
        },
        "overlap_with_shallow_weighted_closures": 0,
        "source_gap_count": manifest["audited_gap_count"],
        "claim_limit": "Pending separate exact checker; no ancestor aggregation is performed.",
    }
    SUMMARY.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", type=int, default=1, choices=(1, 2, 3, 4))
    args = parser.parse_args()
    print(json.dumps(run(args.workers), indent=2, sort_keys=True))

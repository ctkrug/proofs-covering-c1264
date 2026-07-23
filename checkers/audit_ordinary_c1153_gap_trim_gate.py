#!/usr/bin/env python3
"""Independent exact checker for the ordinary-C(11,5,3) gap-trim gate."""

from __future__ import annotations

import gzip
import hashlib
import itertools
import json
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
AUDIT = TARGET / "gate-512-independent-audit.json"
BLOCKS = tuple(itertools.combinations(range(1, 12), 5))
BLOCK_TRIPLES = tuple(frozenset(itertools.combinations(block, 3)) for block in BLOCKS)
TRIPLES = tuple(itertools.combinations(range(1, 12), 3))
TRIPLE_COVERERS = {
    triple: frozenset(
        index + 1 for index, covered in enumerate(BLOCK_TRIPLES) if triple in covered
    )
    for triple in TRIPLES
}


def compact(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def sha_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def object_sha(value: object) -> str:
    return sha_bytes(compact(value))


def exact_domain_sha(domain: dict[str, object]) -> str:
    return object_sha(
        {
            "fixed": list(domain["fixed"]),
            "forbidden": list(domain["forbidden"]),
            "available": list(domain["available"]),
            "uncovered": [list(row) for row in domain["uncovered"]],
            "remaining_slots": int(domain["remaining_slots"]),
        }
    )


def replay_propagation(
    fixed_input: set[int], forbidden_input: set[int]
) -> tuple[str, set[int], set[int], dict[str, object]]:
    fixed, forbidden, trace = set(fixed_input), set(forbidden_input), []
    while True:
        if fixed & forbidden:
            return "CONTRADICTION_ASSIGNMENT", fixed, forbidden, {"trace": trace}
        available = set(range(1, len(BLOCKS) + 1)) - fixed - forbidden
        if len(fixed) > 20 or len(fixed) + len(available) < 20:
            return "CONTRADICTION_CARDINALITY", fixed, forbidden, {"trace": trace}
        covered = set().union(*(BLOCK_TRIPLES[value - 1] for value in fixed))
        uncovered = [triple for triple in TRIPLES if triple not in covered]
        coverers = {
            triple: sorted(TRIPLE_COVERERS[triple] & available) for triple in uncovered
        }
        empty = next((triple for triple in uncovered if not coverers[triple]), None)
        if empty is not None:
            return "CONTRADICTION_COVERAGE", fixed, forbidden, {
                "trace": trace,
                "empty_triple": list(empty),
            }
        if len(fixed) == 20:
            return (
                "SAT_COVER" if not uncovered else "CONTRADICTION_COVERAGE",
                fixed,
                forbidden,
                {"trace": trace, "uncovered": [list(row) for row in uncovered]},
            )
        singleton = min(
            (
                (values[0], triple)
                for triple, values in coverers.items()
                if len(values) == 1
            ),
            default=None,
        )
        if singleton is not None:
            variable, triple = singleton
            trace.append(
                {
                    "rule": "SINGLE_COVERER",
                    "triple": list(triple),
                    "variable": variable,
                }
            )
            fixed.add(variable)
            continue
        if len(available) == 20 - len(fixed):
            added = sorted(available)
            trace.append({"rule": "CARDINALITY_FILL", "variables": added})
            fixed.update(available)
            continue
        return "OPEN", fixed, forbidden, {
            "trace": trace,
            "uncovered": [list(row) for row in uncovered],
            "coverers": {"-".join(map(str, key)): value for key, value in coverers.items()},
        }


def check_propagation(
    receipt: dict[str, object], fixed: set[int], forbidden: set[int]
) -> tuple[str, set[int], set[int], dict[str, object]]:
    replayed = replay_propagation(fixed, forbidden)
    expected = {
        "status": replayed[0],
        "fixed": sorted(replayed[1]),
        "forbidden": sorted(replayed[2]),
        "detail": replayed[3],
    }
    if receipt != expected:
        raise ValueError("propagation receipt mismatch")
    return replayed


def check_dominance(
    receipt: dict[str, object], uncovered: list[tuple[int, ...]], available: list[int]
) -> list[tuple[int, ...]]:
    retained = [tuple(row) for row in receipt["retained_triples"]]
    dropped = {tuple(row["dropped_triple"]): row for row in receipt["dropped_rows"]}
    if set(retained) | set(dropped) != set(uncovered) or set(retained) & set(dropped):
        raise ValueError("dominance rows are not an exact partition")
    coverers = {
        triple: sorted(
            value for value in available if triple in BLOCK_TRIPLES[value - 1]
        )
        for triple in uncovered
    }
    for triple, row in dropped.items():
        witness = tuple(row["witness_triple"])
        if witness not in retained or not set(coverers[witness]) <= set(coverers[triple]):
            raise ValueError("invalid dominance subset witness")
        if row["dropped_coverers_sha256"] != object_sha(coverers[triple]):
            raise ValueError("dropped coverer hash mismatch")
        if row["witness_coverers_sha256"] != object_sha(coverers[witness]):
            raise ValueError("witness coverer hash mismatch")
    return retained


def check_weighted(
    certificate: dict[str, object] | None,
    uncovered: list[tuple[int, ...]],
    available: list[int],
    slots: int,
) -> bool:
    if certificate is None:
        return False
    allowed = set(uncovered)
    weights: dict[tuple[int, ...], int] = {}
    for row in certificate["weights"]:
        triple, numerator = tuple(row[:3]), row[3]
        if triple not in allowed or triple in weights or not isinstance(numerator, int) or numerator <= 0:
            raise ValueError("invalid weighted row")
        weights[triple] = numerator
    total = sum(weights.values())
    denominator = certificate["denominator"]
    if total != certificate["total_numerator"] or total <= slots * denominator:
        raise ValueError("insufficient weighted total")
    maximum = max(
        (
            sum(
                weight
                for triple, weight in weights.items()
                if triple in BLOCK_TRIPLES[value - 1]
            )
            for value in available
        ),
        default=0,
    )
    if maximum != certificate["maximum_eligible_block_load"] or maximum > denominator:
        raise ValueError("weighted block overload")
    return True


def open_domain(
    fixed: set[int], forbidden: set[int], detail: dict[str, object]
) -> dict[str, object]:
    return {
        "fixed": sorted(fixed),
        "forbidden": sorted(forbidden),
        "available": sorted(set(range(1, len(BLOCKS) + 1)) - fixed - forbidden),
        "uncovered": [list(row) for row in detail["uncovered"]],
        "remaining_slots": 20 - len(fixed),
    }


def audit() -> dict[str, object]:
    started = time.perf_counter()
    manifest = json.loads(MANIFEST.read_text())
    protocol = json.loads(PROTOCOL.read_text())
    summary = json.loads(SUMMARY.read_text())
    corpus_raw = CORPUS.read_bytes()
    results_raw = RESULTS.read_bytes()
    if sha_bytes(corpus_raw) != manifest["corpus"]["sha256"]:
        raise ValueError("corpus binding mismatch")
    if sha_bytes(PROTOCOL.read_bytes()) != summary["protocol_sha256"]:
        raise ValueError("protocol binding mismatch")
    if sha_bytes(results_raw) != summary["results"]["sha256"]:
        raise ValueError("results archive binding mismatch")
    corpus = {
        row["case_id"]: row
        for row in (
            json.loads(line) for line in gzip.decompress(corpus_raw).splitlines()
        )
    }
    outcomes = [
        json.loads(line) for line in gzip.decompress(results_raw).splitlines()
    ]
    if [row["case_id"] for row in outcomes] != protocol["sample_case_ids"]:
        raise ValueError("sample result membership mismatch")
    if object_sha(protocol["sample_case_ids"]) != protocol["sample_case_ids_sha256"]:
        raise ValueError("sample identity hash mismatch")

    jobs = {row["case_id"]: row for row in all_open_jobs()}
    source = json.loads((BASE / "manifest.json").read_text())
    cases = {row["id"]: row for row in source["target_cases"]}
    _, parents, _, _ = reconstruct_hierarchy()
    checked_terminal = 0
    methods = Counter()
    check_times = []
    for result in outcomes:
        case_started = time.perf_counter()
        case_id = result["case_id"]
        gap = corpus[case_id]
        job = jobs[case_id]
        case = cases[job["target_child_id"]]
        parent_id = Path(case["third_level_parent_cnf"]["path"]).parent.name
        domain = residual_domain(job, case, parents[parent_id])
        if exact_domain_sha(domain) != gap["exact_residual_domain_sha256"]:
            raise ValueError(f"{case_id}: reconstructed source domain mismatch")
        status, fixed, forbidden, detail = check_propagation(
            result["initial_propagation"],
            set(domain["fixed"]),
            set(domain["forbidden"]),
        )
        terminal = status.startswith("CONTRADICTION")
        if status == "OPEN":
            propagated = open_domain(fixed, forbidden, detail)
            if result["propagated_domain_sha256"] != exact_domain_sha(propagated):
                raise ValueError(f"{case_id}: propagated domain hash mismatch")
            retained = check_dominance(
                result["dominance"],
                [tuple(row) for row in propagated["uncovered"]],
                propagated["available"],
            )
            weighted = check_weighted(
                result["post_propagation_weighted"]["certificate"],
                retained,
                propagated["available"],
                propagated["remaining_slots"],
            )
            terminal = weighted
            if not weighted:
                partition = result["two_layer_partition"]
                selected = tuple(partition["selected_triple"])
                coverers = sorted(
                    value
                    for value in propagated["available"]
                    if selected in BLOCK_TRIPLES[value - 1]
                )
                if partition["coverers"] != coverers or partition["child_count"] != len(coverers):
                    raise ValueError(f"{case_id}: partition coverer mismatch")
                expected_selected = min(
                    retained,
                    key=lambda row: (
                        sum(
                            row in BLOCK_TRIPLES[value - 1]
                            for value in propagated["available"]
                        ),
                        row,
                    ),
                )
                if selected != expected_selected:
                    raise ValueError(f"{case_id}: partition triple rule mismatch")
                if partition["complete"]:
                    if len(partition["children"]) != len(coverers):
                        raise ValueError(f"{case_id}: incomplete child list")
                    all_terminal = True
                    earlier: set[int] = set()
                    for index, (variable, child) in enumerate(
                        zip(coverers, partition["children"])
                    ):
                        if (
                            child["index"] != index
                            or child["fixed_variable"] != variable
                            or child["earlier_forbidden"] != sorted(earlier)
                        ):
                            raise ValueError(f"{case_id}: child first-occupied mismatch")
                        child_status, child_fixed, child_forbidden, child_detail = check_propagation(
                            child["propagation"],
                            fixed | {variable},
                            forbidden | earlier,
                        )
                        child_terminal = child_status.startswith("CONTRADICTION")
                        if child_status == "OPEN":
                            child_domain = open_domain(
                                child_fixed, child_forbidden, child_detail
                            )
                            if child["domain_sha256"] != exact_domain_sha(child_domain):
                                raise ValueError(f"{case_id}: child domain hash mismatch")
                            child_retained = check_dominance(
                                child["dominance"],
                                [tuple(row) for row in child_domain["uncovered"]],
                                child_domain["available"],
                            )
                            child_terminal = check_weighted(
                                child["weighted"]["certificate"],
                                child_retained,
                                child_domain["available"],
                                child_domain["remaining_slots"],
                            )
                        if child_terminal != child["terminal"]:
                            raise ValueError(f"{case_id}: child terminal mismatch")
                        all_terminal &= child_terminal
                        earlier.add(variable)
                    if partition["all_children_terminal"] != all_terminal:
                        raise ValueError(f"{case_id}: partition aggregation mismatch")
                    terminal = all_terminal
        if result["terminal"] != terminal:
            raise ValueError(f"{case_id}: formula terminal mismatch")
        checked_terminal += terminal
        methods[result["method"]] += 1
        check_times.append(time.perf_counter() - case_started)
    if checked_terminal != summary["terminal_formula_count"]:
        raise ValueError("summary terminal count mismatch")
    report = {
        "schema_version": 1,
        "status": "VALID",
        "manifest_sha256": sha_bytes(MANIFEST.read_bytes()),
        "protocol_sha256": sha_bytes(PROTOCOL.read_bytes()),
        "summary_sha256": sha_bytes(SUMMARY.read_bytes()),
        "results_sha256": sha_bytes(results_raw),
        "sample_size": len(outcomes),
        "independently_checked_terminal_formulas": checked_terminal,
        "open_formulas": len(outcomes) - checked_terminal,
        "counts_by_method": dict(sorted(methods.items())),
        "median_check_seconds": statistics.median(check_times),
        "maximum_check_seconds": max(check_times),
        "total_check_seconds": time.perf_counter() - started,
        "claim_limit": (
            "Exact formula-level contradictions only. No ancestor closure is inferred."
        ),
    }
    AUDIT.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return report


if __name__ == "__main__":
    print(json.dumps(audit(), indent=2, sort_keys=True))

#!/usr/bin/env python3
"""Exact helpers for the read-only ordinary-C(11,5,3) gap-trim lane."""

from __future__ import annotations

import hashlib
import itertools
import json
import math
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "checkers")]

from build_ordinary_c1153_multi_deficit_gate import primary_units, second_units  # noqa: E402
from ordinary_c1153_weighted_backend_v2 import exact_check, solve_highs  # noqa: E402
from run_ordinary_c1153_shallow_weighted_scale import exact_certificate  # noqa: E402


BLOCKS = tuple(itertools.combinations(range(1, 12), 5))
BLOCK_TRIPLES = tuple(frozenset(itertools.combinations(block, 3)) for block in BLOCKS)
TRIPLES = tuple(itertools.combinations(range(1, 12), 3))
TRIPLE_COVERERS = {
    triple: frozenset(
        index + 1 for index, covered in enumerate(BLOCK_TRIPLES) if triple in covered
    )
    for triple in TRIPLES
}
TRIPLE_INDEX = {triple: index for index, triple in enumerate(TRIPLES)}
BLOCK_TRIPLE_MASKS = tuple(
    sum(1 << TRIPLE_INDEX[triple] for triple in covered)
    for covered in BLOCK_TRIPLES
)
TRIPLE_COVERER_MASKS = {
    triple: sum(1 << (variable - 1) for variable in variables)
    for triple, variables in TRIPLE_COVERERS.items()
}


def values_mask(values: set[int] | list[int]) -> int:
    return sum(1 << (value - 1) for value in values)


def mask_values(mask: int) -> list[int]:
    values: list[int] = []
    while mask:
        low = mask & -mask
        values.append(low.bit_length())
        mask ^= low
    return values


def compact(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def object_sha(value: object) -> str:
    return hashlib.sha256(compact(value)).hexdigest()


def exact_domain_identity(domain: dict[str, object]) -> dict[str, object]:
    return {
        "fixed": list(domain["fixed"]),
        "forbidden": list(domain["forbidden"]),
        "available": list(domain["available"]),
        "uncovered": [list(row) for row in domain["uncovered"]],
        "remaining_slots": int(domain["remaining_slots"]),
    }


def exact_domain_sha(domain: dict[str, object]) -> str:
    return object_sha(exact_domain_identity(domain))


def domain_component_hashes(domain: dict[str, object]) -> dict[str, object]:
    return {
        "fixed_sha256": object_sha(domain["fixed"]),
        "forbidden_sha256": object_sha(domain["forbidden"]),
        "available_sha256": object_sha(domain["available"]),
        "uncovered_sha256": object_sha(domain["uncovered"]),
        "unit_recipe_sha256": object_sha(domain["units"]),
        "remaining_slots": domain["remaining_slots"],
    }


def propagate_exact(
    fixed_input: set[int], forbidden_input: set[int]
) -> tuple[str, set[int], set[int], dict[str, object]]:
    """Coverage/cardinality propagation with a replayable step trace."""
    fixed = set(fixed_input)
    forbidden = set(forbidden_input)
    trace: list[dict[str, object]] = []
    while True:
        if fixed & forbidden:
            return "CONTRADICTION_ASSIGNMENT", fixed, forbidden, {"trace": trace}
        available = set(range(1, len(BLOCKS) + 1)) - fixed - forbidden
        if len(fixed) > 20 or len(fixed) + len(available) < 20:
            return "CONTRADICTION_CARDINALITY", fixed, forbidden, {"trace": trace}
        covered = set().union(*(BLOCK_TRIPLES[value - 1] for value in fixed))
        uncovered = [triple for triple in TRIPLES if triple not in covered]
        available_mask = values_mask(available)
        coverers = {
            triple: mask_values(TRIPLE_COVERER_MASKS[triple] & available_mask)
            for triple in uncovered
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


def dominance_reduce(
    uncovered: list[tuple[int, ...]], available: list[int]
) -> tuple[list[tuple[int, ...]], list[dict[str, object]]]:
    """Remove only coverage rows logically implied by a stronger coverage row."""
    available_mask = values_mask(available)
    coverers = {
        triple: TRIPLE_COVERER_MASKS[triple] & available_mask for triple in uncovered
    }
    kept: list[tuple[int, ...]] = []
    dropped: list[dict[str, object]] = []
    ordered = sorted(uncovered, key=lambda row: (coverers[row].bit_count(), row))
    for triple in ordered:
        witness = next(
            (
                other
                for other in kept
                if coverers[other] & ~coverers[triple] == 0
            ),
            None,
        )
        if witness is None:
            kept.append(triple)
        else:
            dropped.append(
                {
                    "dropped_triple": list(triple),
                    "witness_triple": list(witness),
                    "dropped_coverers_sha256": object_sha(mask_values(coverers[triple])),
                    "witness_coverers_sha256": object_sha(mask_values(coverers[witness])),
                }
            )
    return sorted(kept), sorted(dropped, key=lambda row: row["dropped_triple"])


def weighted_proposal(
    uncovered: list[tuple[int, ...]],
    available: list[int],
    remaining_slots: int,
    seconds: float = 1.0,
) -> tuple[dict[str, object] | None, dict[str, object]]:
    status, duals, elapsed = solve_highs(uncovered, available, seconds)
    certificate = (
        exact_certificate(duals, available, remaining_slots)
        if status == "Optimal"
        else None
    )
    domain = {
        "uncovered": [list(row) for row in uncovered],
        "available": list(available),
        "remaining_slots": remaining_slots,
    }
    if certificate is not None and not exact_check(domain, certificate):
        raise ValueError("weighted proposal failed its exact acceptance check")
    return certificate, {"lp_status": status, "lp_runtime_seconds": elapsed}


def residual_isomorphism_sha(domain: dict[str, object]) -> str:
    """Exact colored-incidence-graph canonical certificate under point relabeling."""
    import pynauty

    fixed = list(domain["fixed"])
    available = list(domain["available"])
    uncovered = [tuple(row) for row in domain["uncovered"]]
    point_start = 0
    fixed_start = 11
    available_start = fixed_start + len(fixed)
    triple_start = available_start + len(available)
    count = triple_start + len(uncovered)
    adjacency: dict[int, list[int]] = {index: [] for index in range(count)}

    def attach(vertex: int, points: tuple[int, ...]) -> None:
        for point in points:
            pvertex = point_start + point - 1
            adjacency[vertex].append(pvertex)
            adjacency[pvertex].append(vertex)

    for offset, variable in enumerate(fixed):
        attach(fixed_start + offset, BLOCKS[variable - 1])
    for offset, variable in enumerate(available):
        attach(available_start + offset, BLOCKS[variable - 1])
    for offset, triple in enumerate(uncovered):
        attach(triple_start + offset, triple)
    coloring = [
        set(range(point_start, fixed_start)),
        set(range(fixed_start, available_start)),
        set(range(available_start, triple_start)),
        set(range(triple_start, count)),
    ]
    graph = pynauty.Graph(
        number_of_vertices=count,
        directed=False,
        adjacency_dict=adjacency,
        vertex_coloring=[cell for cell in coloring if cell],
    )
    return hashlib.sha256(pynauty.certificate(graph)).hexdigest()


def structural_features(domain: dict[str, object]) -> dict[str, object]:
    fixed = list(domain["fixed"])
    available = list(domain["available"])
    uncovered = [tuple(row) for row in domain["uncovered"]]
    available_mask = values_mask(available)
    coverer_counts = [
        (TRIPLE_COVERER_MASKS[triple] & available_mask).bit_count()
        for triple in uncovered
    ]
    fixed_point = [
        sum(point in BLOCKS[value - 1] for value in fixed) for point in range(1, 12)
    ]
    available_point = [
        sum(point in BLOCKS[value - 1] for value in available) for point in range(1, 12)
    ]
    pairs = tuple(itertools.combinations(range(1, 12), 2))
    fixed_pair = [
        sum(set(pair) <= set(BLOCKS[value - 1]) for value in fixed) for pair in pairs
    ]
    available_pair = [
        sum(set(pair) <= set(BLOCKS[value - 1]) for value in available) for pair in pairs
    ]
    return {
        "remaining_slots": domain["remaining_slots"],
        "fixed_block_count": len(fixed),
        "uncovered_triple_count": len(uncovered),
        "available_block_count": len(available),
        "min_eligible_coverers": min(coverer_counts, default=0),
        "median_eligible_coverers": sorted(coverer_counts)[len(coverer_counts) // 2]
        if coverer_counts
        else 0,
        "max_eligible_coverers": max(coverer_counts, default=0),
        "fixed_point_degrees": sorted(fixed_point),
        "available_point_capacities": sorted(available_point),
        "fixed_pair_multiplicities": sorted(fixed_pair),
        "available_pair_capacities": sorted(available_pair),
        "isomorphism_sha256": residual_isomorphism_sha(domain),
    }


def state_domain(
    fixed: set[int],
    forbidden: set[int],
    detail: dict[str, object],
) -> dict[str, object]:
    if "uncovered" not in detail:
        raise ValueError("an open propagated state must list uncovered triples")
    return {
        "fixed": sorted(fixed),
        "forbidden": sorted(forbidden),
        "available": sorted(set(range(1, len(BLOCKS) + 1)) - fixed - forbidden),
        "uncovered": [list(row) for row in detail["uncovered"]],
        "remaining_slots": 20 - len(fixed),
    }


def initial_sets(case: dict[str, object], second_index: int, parent_raw: bytes) -> tuple[set[int], set[int]]:
    parent_fixed, parent_forbidden = primary_units(parent_raw)
    inherited = [*case["inherited_units"], *second_units(case, second_index)]
    return (
        parent_fixed | {value for value in inherited if value > 0},
        parent_forbidden | {-value for value in inherited if value < 0},
    )

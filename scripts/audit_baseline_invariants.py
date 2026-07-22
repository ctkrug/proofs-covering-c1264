#!/usr/bin/env python3
"""Deterministic arithmetic and witness audit for the C(12,6,4) baseline."""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import math
from pathlib import Path


POINTS = tuple(range(12))
MATCHING = ((0, 1), (2, 3), (4, 5), (6, 7), (8, 9), (10, 11))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_blocks(path: Path) -> list[tuple[int, ...]]:
    blocks: list[tuple[int, ...]] = []
    for line_number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        block = tuple(int(value) - 1 for value in raw.split())
        if len(block) != 6 or tuple(sorted(set(block))) != block:
            raise ValueError(f"line {line_number}: not a strictly increasing 6-subset")
        if block[0] < 0 or block[-1] >= 12:
            raise ValueError(f"line {line_number}: point outside 1..12")
        blocks.append(block)
    if len(blocks) != len(set(blocks)):
        raise ValueError("duplicate witness block")
    return blocks


def enumerate_matchings(points: tuple[int, ...]) -> int:
    if not points:
        return 1
    first = points[0]
    total = 0
    for index in range(1, len(points)):
        total += enumerate_matchings(points[1:index] + points[index + 1 :])
    return total


def r_value(block: tuple[int, ...]) -> int:
    block_set = set(block)
    return sum(set(pair) <= block_set for pair in MATCHING)


def degree_profiles() -> list[list[int]]:
    profiles: list[list[int]] = []
    for n0 in range(41):
        for n1 in range(41 - n0):
            for n2 in range(41 - n0 - n1):
                n3 = 40 - n0 - n1 - n2
                if n1 + 2 * n2 + 3 * n3 == 60:
                    profiles.append([n0, n1, n2, n3])
    return profiles


def audit(witness: Path) -> dict[str, object]:
    blocks = load_blocks(witness)
    candidates = list(itertools.combinations(POINTS, 6))
    targets = list(itertools.combinations(POINTS, 4))
    covered = {target for block in blocks for target in itertools.combinations(block, 4)}
    if len(blocks) != 41 or len(covered) != len(targets):
        raise ValueError("frozen witness is not a 41-block C(12,6,4) cover")

    dropped_covered = {
        target for block in blocks[1:] for target in itertools.combinations(block, 4)
    }
    point_degrees = [sum(point in block for block in blocks) for point in POINTS]
    pair_multiplicities = [
        sum(a in block and b in block for block in blocks)
        for a, b in itertools.combinations(POINTS, 2)
    ]

    matching_count = enumerate_matchings(POINTS)
    matching_formula = math.factorial(12) // (2**6 * math.factorial(6))
    if matching_count != matching_formula:
        raise AssertionError("matching enumeration/formula disagreement")

    class_counts = {str(r): 0 for r in range(4)}
    for block in candidates:
        class_counts[str(r_value(block))] += 1
    profiles = degree_profiles()
    if any(profile[0] == 0 and profile[1] == 0 for profile in profiles):
        raise AssertionError("root split fails for a feasible r-profile")

    point_lower = 20  # C(11,5,3), maintained exact value.
    pair_lower = 9  # C(10,4,2), maintained exact value.
    hypothetical = {
        "blocks": 40,
        "point_incidence_total": 40 * 6,
        "point_degree_lower": point_lower,
        "forced_point_degrees": [point_lower] * 12,
        "pair_incidence_total": 40 * math.comb(6, 2),
        "pair_multiplicity_lower": pair_lower,
        "pair_baseline_total": math.comb(12, 2) * pair_lower,
        "pair_excess_total": 40 * math.comb(6, 2) - math.comb(12, 2) * pair_lower,
        "pair_sum_at_each_point": 5 * point_lower,
        "pair_excess_degree_at_each_point": 5 * point_lower - 11 * pair_lower,
        "forced_excess_graph": "1-regular simple graph: six disjoint multiplicity-10 pairs",
        "matching_count": matching_count,
        "matching_stabilizer_order": 2**6 * math.factorial(6),
        "matching_quotient_factor": matching_count,
        "fixed_matching": [list(pair) for pair in MATCHING],
        "sum_complete_matching_pairs_over_blocks": 6 * 10,
        "block_r_class_counts": class_counts,
        "feasible_r_profiles": profiles,
        "root_split": "r=0 present, or r=0 absent and r=1 present",
    }

    incidence_edges = len(candidates) * math.comb(6, 4)
    result: dict[str, object] = {
        "schema_version": 1,
        "status": "valid-baseline-audit",
        "claim_limit": (
            "Validates sourced arithmetic consequences and the published 41-block control; "
            "does not search for or exclude a 40-block cover."
        ),
        "parameters": {"v": 12, "k": 6, "t": 4},
        "incidence_universe": {
            "candidate_blocks": len(candidates),
            "targets": len(targets),
            "targets_per_block": math.comb(6, 4),
            "blocks_per_target": math.comb(8, 2),
            "incidence_edges": incidence_edges,
            "double_count_check": len(targets) * math.comb(8, 2),
        },
        "published_control": {
            "blocks": len(blocks),
            "covered_targets": len(covered),
            "point_degree_range": [min(point_degrees), max(point_degrees)],
            "pair_multiplicity_range": [min(pair_multiplicities), max(pair_multiplicities)],
            "witness_path": str(witness),
            "witness_sha256": sha256(witness),
        },
        "negative_control": {
            "transformation": "delete first published block",
            "remaining_blocks": len(blocks) - 1,
            "covered_targets": len(dropped_covered),
            "uncovered_targets": len(targets) - len(dropped_covered),
            "passes_cover_check": len(dropped_covered) == len(targets),
        },
        "hypothetical_40_consequences": hypothetical,
        "source_urls": [
            "https://ljcr.dmgordon.org/cover/show_cover.php?v=12&k=6&t=4",
            "https://ljcr.dmgordon.org/cover/show_cover.php?v=11&k=5&t=3",
            "https://ljcr.dmgordon.org/cover/show_cover.php?v=10&k=4&t=2",
            "https://msp.org/pjm/1964/14-4/pjm-v14-n4-p29-p.pdf",
        ],
    }
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--witness", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = audit(args.witness)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "status": result["status"]}, sort_keys=True))


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Independent bitmask checker for the C(12,6,4) baseline audit."""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import math
from pathlib import Path


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def witness_masks(path: Path) -> list[int]:
    masks: list[int] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        values = [int(value) for value in raw.split()]
        if len(values) != 6 or len(set(values)) != 6 or not all(1 <= value <= 12 for value in values):
            raise ValueError("malformed witness")
        masks.append(sum(1 << (value - 1) for value in values))
    if len(masks) != len(set(masks)):
        raise ValueError("duplicate witness block")
    return masks


def subset_masks(n: int, size: int) -> list[int]:
    return [sum(1 << point for point in item) for item in itertools.combinations(range(n), size)]


def matching_dp(n: int) -> int:
    values = [0] * (n + 1)
    values[0] = 1
    for even in range(2, n + 1, 2):
        values[even] = (even - 1) * values[even - 2]
    return values[n]


def verify(result_path: Path, witness_path: Path) -> dict[str, object]:
    result = json.loads(result_path.read_text(encoding="utf-8"))
    blocks = witness_masks(witness_path)
    targets = subset_masks(12, 4)
    candidates = subset_masks(12, 6)
    covered = {target for target in targets if any(block & target == target for block in blocks)}
    dropped = {target for target in targets if any(block & target == target for block in blocks[1:])}
    if len(blocks) != 41 or len(covered) != 495:
        raise AssertionError("published positive control failed bitmask replay")

    canonical_pairs = [0b11 << (2 * index) for index in range(6)]
    class_counts = [0, 0, 0, 0]
    for block in candidates:
        r = sum(block & pair == pair for pair in canonical_pairs)
        class_counts[r] += 1

    profiles: list[list[int]] = []
    for n0 in range(41):
        for n1 in range(41 - n0):
            for n2 in range(41 - n0 - n1):
                n3 = 40 - n0 - n1 - n2
                if n1 + 2 * n2 + 3 * n3 == 60:
                    profiles.append([n0, n1, n2, n3])

    expected = {
        "candidate_blocks": math.comb(12, 6),
        "targets": math.comb(12, 4),
        "incidence_edges": math.comb(12, 6) * math.comb(6, 4),
        "matching_count": matching_dp(12),
        "matching_stabilizer": math.prod((2, 4, 6, 8, 10, 12)),
        "class_counts": class_counts,
        "profiles": profiles,
    }
    observed_universe = result["incidence_universe"]
    consequences = result["hypothetical_40_consequences"]
    control = result["published_control"]
    negative = result["negative_control"]

    checks = {
        "candidate_count": observed_universe["candidate_blocks"] == expected["candidate_blocks"],
        "target_count": observed_universe["targets"] == expected["targets"],
        "incidence_double_count": (
            observed_universe["incidence_edges"]
            == observed_universe["double_count_check"]
            == expected["incidence_edges"]
        ),
        "witness_hash": control["witness_sha256"] == digest(witness_path),
        "positive_control": control["blocks"] == 41 and control["covered_targets"] == len(covered),
        "negative_control": (
            negative["covered_targets"] == len(dropped)
            and negative["uncovered_targets"] == 495 - len(dropped)
            and negative["passes_cover_check"] is False
        ),
        "point_forcing": (
            consequences["point_incidence_total"] == 12 * consequences["point_degree_lower"] == 240
        ),
        "pair_excess": (
            consequences["pair_incidence_total"] == 600
            and consequences["pair_baseline_total"] == 594
            and consequences["pair_excess_total"] == 6
            and consequences["pair_excess_degree_at_each_point"] == 1
        ),
        "matching_quotient": (
            consequences["matching_count"] == expected["matching_count"] == 10_395
            and consequences["matching_stabilizer_order"] == expected["matching_stabilizer"] == 46_080
            and expected["matching_count"] * expected["matching_stabilizer"] == math.factorial(12)
        ),
        "block_classes": (
            [consequences["block_r_class_counts"][str(index)] for index in range(4)]
            == expected["class_counts"]
            == [64, 480, 360, 20]
        ),
        "root_split": (
            consequences["feasible_r_profiles"] == expected["profiles"]
            and all(profile[0] > 0 or profile[1] > 0 for profile in profiles)
        ),
    }
    if not all(checks.values()):
        raise AssertionError({name: value for name, value in checks.items() if not value})
    return {
        "schema_version": 1,
        "status": "valid-independent-check",
        "claim_limit": "Checks only the baseline audit and 41-block control, not C(12,6,4)=40 or 41.",
        "checks": checks,
        "result_path": str(result_path),
        "result_sha256": digest(result_path),
        "witness_path": str(witness_path),
        "witness_sha256": digest(witness_path),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--result", type=Path, required=True)
    parser.add_argument("--witness", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    receipt = verify(args.result, args.witness)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "status": receipt["status"]}, sort_keys=True))


if __name__ == "__main__":
    main()

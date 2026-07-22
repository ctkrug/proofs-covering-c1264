#!/usr/bin/env python3
"""Bounded deterministic repair search for a 40-block C(12,6,4) witness.

The search starts from each 40-block deletion of the published 41-cover and
uses one-block replacements biased toward uncovered quadruples.  Point-degree
and pair-deficit terms guide the search, but only direct coverage validation can
declare success.  No symmetry restriction is imposed on candidate witnesses.
"""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import math
import random
import time
from pathlib import Path


POINTS = tuple(range(12))
ROOT = Path(__file__).resolve().parents[1]
BLOCKS = list(itertools.combinations(POINTS, 6))
QUADS = list(itertools.combinations(POINTS, 4))
PAIRS = list(itertools.combinations(POINTS, 2))
BLOCK_INDEX = {block: index for index, block in enumerate(BLOCKS)}
QUAD_INDEX = {quad: index for index, quad in enumerate(QUADS)}
PAIR_INDEX = {pair: index for index, pair in enumerate(PAIRS)}
BLOCK_QUADS = [tuple(QUAD_INDEX[q] for q in itertools.combinations(block, 4)) for block in BLOCKS]
BLOCK_PAIRS = [tuple(PAIR_INDEX[p] for p in itertools.combinations(block, 2)) for block in BLOCKS]
QUAD_BLOCKS = [
    tuple(index for index, block in enumerate(BLOCKS) if set(quad).issubset(block))
    for quad in QUADS
]


def read_blocks(path: Path) -> list[int]:
    selected: list[int] = []
    for line_number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        block = tuple(int(value) - 1 for value in raw.split())
        if block not in BLOCK_INDEX:
            raise ValueError(f"line {line_number}: not a six-subset of 1..12")
        selected.append(BLOCK_INDEX[block])
    if len(selected) != 41 or len(set(selected)) != 41:
        raise ValueError("warm start must contain 41 distinct blocks")
    return selected


def counts(selected: set[int]) -> tuple[list[int], list[int], list[int]]:
    quad_counts = [0] * len(QUADS)
    point_counts = [0] * len(POINTS)
    pair_counts = [0] * len(PAIRS)
    for block_index in selected:
        for quad in BLOCK_QUADS[block_index]:
            quad_counts[quad] += 1
        for point in BLOCKS[block_index]:
            point_counts[point] += 1
        for pair in BLOCK_PAIRS[block_index]:
            pair_counts[pair] += 1
    return quad_counts, point_counts, pair_counts


def metrics(quad_counts: list[int], point_counts: list[int], pair_counts: list[int]) -> dict[str, int]:
    return {
        "uncovered_quadruples": sum(value == 0 for value in quad_counts),
        "point_degree_deviation": sum(abs(value - 20) for value in point_counts),
        "pair_deficit_below_9": sum(max(0, 9 - value) for value in pair_counts),
        "pair_excess_above_10": sum(max(0, value - 10) for value in pair_counts),
    }


def energy(values: dict[str, int]) -> int:
    return (
        1000 * values["uncovered_quadruples"]
        + 12 * values["point_degree_deviation"]
        + 4 * values["pair_deficit_below_9"]
        + 8 * values["pair_excess_above_10"]
    )


def apply_swap(
    remove: int,
    add: int,
    quad_counts: list[int],
    point_counts: list[int],
    pair_counts: list[int],
    direction: int,
) -> None:
    for quad in BLOCK_QUADS[remove]:
        quad_counts[quad] -= direction
    for quad in BLOCK_QUADS[add]:
        quad_counts[quad] += direction
    for point in BLOCKS[remove]:
        point_counts[point] -= direction
    for point in BLOCKS[add]:
        point_counts[point] += direction
    for pair in BLOCK_PAIRS[remove]:
        pair_counts[pair] -= direction
    for pair in BLOCK_PAIRS[add]:
        pair_counts[pair] += direction


def write_candidate(path: Path, selected: set[int]) -> None:
    payload = "".join(" ".join(str(point + 1) for point in BLOCKS[index]) + "\n" for index in sorted(selected))
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(payload, encoding="utf-8")
    temporary.replace(path)


def portable_path(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def run(source: Path, output: Path, seconds: float, seed: int) -> dict[str, object]:
    if seconds <= 0:
        raise ValueError("seconds must be positive")
    source = source.resolve()
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    warm = read_blocks(source)
    rng = random.Random(seed)
    started = time.monotonic()
    deadline = started + seconds
    iterations = 0
    restarts = 0
    accepted = 0
    best_selected: set[int] | None = None
    best_metrics: dict[str, int] | None = None
    best_energy = math.inf

    deletion_order = list(range(41))
    rng.shuffle(deletion_order)
    while time.monotonic() < deadline:
        removed_warm = deletion_order[restarts % len(deletion_order)]
        selected = set(warm)
        selected.remove(warm[removed_warm])
        quad_counts, point_counts, pair_counts = counts(selected)
        current_metrics = metrics(quad_counts, point_counts, pair_counts)
        current_energy = energy(current_metrics)
        temperature = 800.0
        stagnant = 0
        restarts += 1

        while time.monotonic() < deadline and stagnant < 25_000:
            iterations += 1
            missing = [index for index, value in enumerate(quad_counts) if value == 0]
            if not missing:
                best_selected = set(selected)
                best_metrics = current_metrics
                best_energy = current_energy
                break
            target_quad = rng.choice(missing)
            add_pool = [index for index in QUAD_BLOCKS[target_quad] if index not in selected]
            add = rng.choice(add_pool)
            # Prefer removing a block with little unique coverage, while keeping
            # occasional random moves to escape deterministic local minima.
            removal_sample = rng.sample(tuple(selected), min(12, len(selected)))
            if rng.random() < 0.85:
                remove = min(
                    removal_sample,
                    key=lambda index: sum(quad_counts[q] == 1 for q in BLOCK_QUADS[index]),
                )
            else:
                remove = rng.choice(removal_sample)

            apply_swap(remove, add, quad_counts, point_counts, pair_counts, 1)
            proposed_metrics = metrics(quad_counts, point_counts, pair_counts)
            proposed_energy = energy(proposed_metrics)
            delta = proposed_energy - current_energy
            accept = delta <= 0 or rng.random() < math.exp(-delta / max(temperature, 1.0))
            if accept:
                selected.remove(remove)
                selected.add(add)
                current_metrics = proposed_metrics
                current_energy = proposed_energy
                accepted += 1
                stagnant = 0 if proposed_energy < best_energy else stagnant + 1
                if proposed_energy < best_energy:
                    best_energy = proposed_energy
                    best_metrics = dict(proposed_metrics)
                    best_selected = set(selected)
                    write_candidate(output / "best-candidate.txt", best_selected)
            else:
                apply_swap(remove, add, quad_counts, point_counts, pair_counts, -1)
                stagnant += 1
            temperature = max(5.0, temperature * 0.99985)
        if best_metrics and best_metrics["uncovered_quadruples"] == 0:
            break

    if best_selected is None or best_metrics is None:
        raise AssertionError("search failed to evaluate a state")
    candidate_path = output / "best-candidate.txt"
    write_candidate(candidate_path, best_selected)
    status = "WITNESS_CANDIDATE" if best_metrics["uncovered_quadruples"] == 0 else "NO_WITNESS"
    result = {
        "schema_version": 1,
        "status": status,
        "method": "published-41-cover deletion warm starts plus annealed one-block repair",
        "scope": "unrestricted 40 distinct six-subsets; heuristic and non-exhaustive",
        "seed": seed,
        "seconds_cap": seconds,
        "elapsed_seconds": time.monotonic() - started,
        "iterations": iterations,
        "accepted_moves": accepted,
        "restarts": restarts,
        "best_metrics": best_metrics,
        "source": {"path": portable_path(source), "sha256": hashlib.sha256(source.read_bytes()).hexdigest()},
        "candidate": {
            "path": portable_path(candidate_path),
            "sha256": hashlib.sha256(candidate_path.read_bytes()).hexdigest(),
            "blocks": len(best_selected),
        },
        "claim_limit": "Only WITNESS_CANDIDATE followed by the independent direct checker can change the upper bound; NO_WITNESS is non-exhaustive.",
    }
    (output / "result.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=Path("sources/ljcr-c1264-41.txt"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seconds", type=float, default=60)
    parser.add_argument("--seed", type=int, default=126440)
    args = parser.parse_args()
    print(json.dumps(run(args.source, args.output, args.seconds, args.seed), sort_keys=True))


if __name__ == "__main__":
    main()

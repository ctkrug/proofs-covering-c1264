#!/usr/bin/env python3
"""Bounded degree-preserving two-block repair for a 40-block cover candidate.

Every move removes two selected blocks and inserts two new blocks with the same
combined point-incidence vector.  Consequently, an exact degree-20 input stays
exact degree-20 throughout.  This explores genuine two-block trades: neither
inserted block may be one of the removed blocks.
"""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import math
import random
import time
from collections import defaultdict
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


def read_candidate(path: Path) -> set[int]:
    selected: list[int] = []
    for line_number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        block = tuple(int(value) - 1 for value in raw.split())
        if block not in BLOCK_INDEX:
            raise ValueError(f"line {line_number}: not a six-subset of 1..12")
        selected.append(BLOCK_INDEX[block])
    if len(selected) != 40 or len(set(selected)) != 40:
        raise ValueError("source must contain 40 distinct blocks")
    return set(selected)


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
        + 4 * values["pair_deficit_below_9"]
        + 8 * values["pair_excess_above_10"]
    )


def signature(first: int, second: int) -> tuple[int, ...]:
    a, b = set(BLOCKS[first]), set(BLOCKS[second])
    return tuple(int(point in a) + int(point in b) for point in POINTS)


def trade_groups() -> dict[tuple[int, ...], tuple[tuple[int, int], ...]]:
    groups: dict[tuple[int, ...], list[tuple[int, int]]] = defaultdict(list)
    for first in range(len(BLOCKS)):
        for second in range(first + 1, len(BLOCKS)):
            groups[signature(first, second)].append((first, second))
    return {key: tuple(value) for key, value in groups.items() if len(value) > 1}


def apply_trade(
    remove: tuple[int, int],
    add: tuple[int, int],
    quad_counts: list[int],
    pair_counts: list[int],
    direction: int,
) -> None:
    for block_index in remove:
        for quad in BLOCK_QUADS[block_index]:
            quad_counts[quad] -= direction
        for pair in BLOCK_PAIRS[block_index]:
            pair_counts[pair] -= direction
    for block_index in add:
        for quad in BLOCK_QUADS[block_index]:
            quad_counts[quad] += direction
        for pair in BLOCK_PAIRS[block_index]:
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
    selected = read_candidate(source)
    quad_counts, point_counts, pair_counts = counts(selected)
    if point_counts != [20] * 12:
        raise ValueError("source must have point degree exactly 20")
    groups = trade_groups()
    rng = random.Random(seed)
    started = time.monotonic()
    deadline = started + seconds
    current_metrics = metrics(quad_counts, point_counts, pair_counts)
    current_energy = energy(current_metrics)
    best_selected = set(selected)
    best_metrics = dict(current_metrics)
    best_energy = current_energy
    iterations = accepted = improving = 0
    # The six-defect warm start is a strict local minimum: its cheapest genuine
    # degree-preserving two-block trade costs about 4,000 energy units.  Start
    # above that measured barrier so the annealer can leave the basin.
    initial_temperature = 6000.0
    temperature = initial_temperature

    while time.monotonic() < deadline:
        iterations += 1
        removals = rng.sample(list(itertools.combinations(sorted(selected), 2)), 20)
        proposals: list[tuple[tuple[int, int], tuple[int, int]]] = []
        for remove in removals:
            for add in groups.get(signature(*remove), ()):
                # Requiring two completely new blocks makes this a genuine
                # two-block neighborhood rather than a disguised one-block move.
                if not set(add) & selected:
                    proposals.append((remove, add))
        if not proposals:
            continue
        remove, add = rng.choice(proposals)
        apply_trade(remove, add, quad_counts, pair_counts, 1)
        proposed_metrics = metrics(quad_counts, point_counts, pair_counts)
        proposed_energy = energy(proposed_metrics)
        delta = proposed_energy - current_energy
        accept = delta <= 0 or rng.random() < math.exp(-delta / max(temperature, 1.0))
        if accept:
            selected.difference_update(remove)
            selected.update(add)
            current_metrics = proposed_metrics
            current_energy = proposed_energy
            accepted += 1
            if proposed_energy < best_energy:
                best_energy = proposed_energy
                best_metrics = dict(proposed_metrics)
                best_selected = set(selected)
                improving += 1
                write_candidate(output / "best-candidate.txt", best_selected)
        else:
            apply_trade(remove, add, quad_counts, pair_counts, -1)
        temperature = max(2.0, temperature * 0.99995)
        if best_metrics["uncovered_quadruples"] == 0:
            break

    candidate_path = output / "best-candidate.txt"
    write_candidate(candidate_path, best_selected)
    status = "WITNESS_CANDIDATE" if best_metrics["uncovered_quadruples"] == 0 else "NO_WITNESS"
    result = {
        "schema_version": 1,
        "status": status,
        "method": "annealed genuine two-block degree-preserving trades",
        "scope": "unrestricted 40 distinct six-subsets from an exact-degree source; heuristic and non-exhaustive",
        "seed": seed,
        "seconds_cap": seconds,
        "elapsed_seconds": time.monotonic() - started,
        "iterations": iterations,
        "accepted_moves": accepted,
        "improving_moves": improving,
        "initial_temperature": initial_temperature,
        "trade_signature_classes": len(groups),
        "best_metrics": best_metrics,
        "source": {"path": portable_path(source), "sha256": hashlib.sha256(source.read_bytes()).hexdigest()},
        "candidate": {
            "path": portable_path(candidate_path),
            "sha256": hashlib.sha256(candidate_path.read_bytes()).hexdigest(),
            "blocks": len(best_selected),
        },
        "claim_limit": "Only WITNESS_CANDIDATE followed by independent direct checking can change the upper bound; NO_WITNESS is non-exhaustive.",
    }
    (output / "result.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seconds", type=float, default=60)
    parser.add_argument("--seed", type=int, default=126450)
    args = parser.parse_args()
    print(json.dumps(run(args.source, args.output, args.seconds, args.seed), sort_keys=True))


if __name__ == "__main__":
    main()

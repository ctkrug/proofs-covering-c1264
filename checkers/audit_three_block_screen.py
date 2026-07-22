#!/usr/bin/env python3
"""Independent direct audit and accepted-trace replay for a three-block screen."""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
POINTS = tuple(range(12))
BLOCKS = list(itertools.combinations(POINTS, 6))
QUADS = list(itertools.combinations(POINTS, 4))
PAIRS = list(itertools.combinations(POINTS, 2))
BLOCK_INDEX = {block: index for index, block in enumerate(BLOCKS)}


def resolve(path: str) -> Path:
    value = Path(path)
    return value if value.is_absolute() else ROOT / value


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def load_blocks(path: Path, expected: int) -> set[int]:
    indices: list[int] = []
    for line_number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        values = tuple(int(value) - 1 for value in raw.split())
        if len(values) != 6 or values != tuple(sorted(set(values))) or values not in BLOCK_INDEX:
            raise ValueError(f"{path}:{line_number}: malformed block")
        indices.append(BLOCK_INDEX[values])
    if len(indices) != expected or len(set(indices)) != expected:
        raise ValueError(f"{path}: expected {expected} distinct blocks")
    return set(indices)


def incidence_signature(indices: tuple[int, ...]) -> tuple[int, ...]:
    return tuple(sum(point in BLOCKS[index] for index in indices) for point in POINTS)


def direct_metrics(selected: set[int]) -> dict[str, int]:
    concrete = [set(BLOCKS[index]) for index in selected]
    quad_counts = [sum(set(quad).issubset(block) for block in concrete) for quad in QUADS]
    point_counts = [sum(point in block for block in concrete) for point in POINTS]
    pair_counts = [sum(set(pair).issubset(block) for block in concrete) for pair in PAIRS]
    return {
        "uncovered_quadruples": sum(value == 0 for value in quad_counts),
        "point_degree_deviation": sum(abs(value - 20) for value in point_counts),
        "pair_deficit_below_9": sum(max(0, 9 - value) for value in pair_counts),
        "pair_excess_above_10": sum(max(0, value - 10) for value in pair_counts),
    }


def independent_counts(selected: set[int]) -> tuple[list[int], list[int], list[int]]:
    quad_position = {quad: index for index, quad in enumerate(QUADS)}
    pair_position = {pair: index for index, pair in enumerate(PAIRS)}
    quad_counts = [0] * len(QUADS)
    point_counts = [0] * len(POINTS)
    pair_counts = [0] * len(PAIRS)
    for index in selected:
        block = BLOCKS[index]
        for quad in itertools.combinations(block, 4):
            quad_counts[quad_position[quad]] += 1
        for point in block:
            point_counts[point] += 1
        for pair in itertools.combinations(block, 2):
            pair_counts[pair_position[pair]] += 1
    return quad_counts, point_counts, pair_counts


def metrics_from_counts(
    quad_counts: list[int], point_counts: list[int], pair_counts: list[int]
) -> dict[str, int]:
    return {
        "uncovered_quadruples": sum(value == 0 for value in quad_counts),
        "point_degree_deviation": sum(abs(value - 20) for value in point_counts),
        "pair_deficit_below_9": sum(max(0, 9 - value) for value in pair_counts),
        "pair_excess_above_10": sum(max(0, value - 10) for value in pair_counts),
    }


def independently_apply(
    quad_counts: list[int],
    point_counts: list[int],
    pair_counts: list[int],
    indices: tuple[int, ...],
    direction: int,
) -> None:
    quad_position = {quad: index for index, quad in enumerate(QUADS)}
    pair_position = {pair: index for index, pair in enumerate(PAIRS)}
    for index in indices:
        block = BLOCKS[index]
        for quad in itertools.combinations(block, 4):
            quad_counts[quad_position[quad]] += direction
        for point in block:
            point_counts[point] += direction
        for pair in itertools.combinations(block, 2):
            pair_counts[pair_position[pair]] += direction


def uncovered(selected: set[int]) -> set[tuple[int, ...]]:
    concrete = [set(BLOCKS[index]) for index in selected]
    return {quad for quad in QUADS if not any(set(quad).issubset(block) for block in concrete)}


def two_block_decomposable(remove: tuple[int, ...], add: tuple[int, ...]) -> bool:
    removed = {incidence_signature(pair) for pair in itertools.combinations(remove, 2)}
    return any(incidence_signature(pair) in removed for pair in itertools.combinations(add, 2))


def audit_seed(result_path: Path) -> dict[str, object]:
    result = json.loads(result_path.read_text(encoding="utf-8"))
    source_path = resolve(result["source"]["path"])
    if digest(source_path) != result["source"]["sha256"]:
        raise ValueError("source hash mismatch")
    selected = load_blocks(source_path, 40)
    quad_counts, point_counts, pair_counts = independent_counts(selected)
    if metrics_from_counts(quad_counts, point_counts, pair_counts) != result["initial_metrics"]:
        raise ValueError("initial metric mismatch")
    chain = result["initial_chain_sha256"]
    trace_path = resolve(result["trace"]["path"])
    if digest(trace_path) != result["trace"]["sha256"]:
        raise ValueError("trace hash mismatch")
    best_selected = set(selected)
    accepted = 0
    for raw in trace_path.read_text(encoding="utf-8").splitlines():
        event = json.loads(raw)
        accepted += 1
        if event["accepted_index"] != accepted:
            raise ValueError("nonconsecutive accepted index")
        remove = tuple(event["remove"])
        add = tuple(event["add"])
        if len(remove) != 3 or len(set(remove)) != 3 or not set(remove) <= selected:
            raise ValueError("invalid removal triple")
        if len(add) != 3 or len(set(add)) != 3 or set(add) & selected:
            raise ValueError("invalid addition triple")
        if incidence_signature(remove) != incidence_signature(add):
            raise ValueError("point-incidence signature not preserved")
        if two_block_decomposable(remove, add):
            raise ValueError("accepted trade decomposes into a legal two-block trade")
        before_missing = {QUADS[index] for index, count in enumerate(quad_counts) if count == 0}
        target_quad = tuple(event["target_quad"])
        if target_quad not in before_missing:
            raise ValueError("recorded target was not uncovered before the move")
        if not any(set(target_quad).issubset(BLOCKS[index]) for index in add):
            raise ValueError("no added block contains the recorded target")
        before = metrics_from_counts(quad_counts, point_counts, pair_counts)
        if before != event["before_metrics"]:
            raise ValueError("before-move metric mismatch")
        selected.difference_update(remove)
        selected.update(add)
        independently_apply(quad_counts, point_counts, pair_counts, remove, -1)
        independently_apply(quad_counts, point_counts, pair_counts, add, 1)
        after = metrics_from_counts(quad_counts, point_counts, pair_counts)
        if after != event["after_metrics"]:
            raise ValueError("after-move metric mismatch")
        base = dict(event)
        recorded_chain = base.pop("chain_sha256")
        chain = hashlib.sha256((chain + "\n" + canonical_json(base)).encode("utf-8")).hexdigest()
        if chain != recorded_chain:
            raise ValueError("trace hash chain mismatch")
        if accepted == result["best_accept_count"]:
            best_selected = set(selected)
    if accepted != result["accepted_moves"] or chain != result["final_chain_sha256"]:
        raise ValueError("final trace receipt mismatch")
    if metrics_from_counts(quad_counts, point_counts, pair_counts) != result["final_metrics"]:
        raise ValueError("final metric mismatch")
    if result["best_accept_count"] == 0:
        best_selected = load_blocks(source_path, 40)
    candidate_path = resolve(result["candidate"]["path"])
    if digest(candidate_path) != result["candidate"]["sha256"]:
        raise ValueError("candidate hash mismatch")
    candidate = load_blocks(candidate_path, 40)
    if candidate != best_selected or direct_metrics(candidate) != result["best_metrics"]:
        raise ValueError("best candidate mismatch")
    expected_status = "WITNESS_CANDIDATE" if result["best_metrics"]["uncovered_quadruples"] == 0 else result["status"]
    if expected_status != result["status"]:
        raise ValueError("status mismatch")
    metamorphic = "not_applicable"
    if result["best_metrics"]["uncovered_quadruples"] == 0:
        permutation = {point: 11 - point for point in POINTS}
        permuted = {BLOCK_INDEX[tuple(sorted(permutation[p] for p in BLOCKS[index]))] for index in candidate}
        if direct_metrics(permuted)["uncovered_quadruples"] != 0:
            raise ValueError("permuted witness failed direct coverage")
        metamorphic = "reverse-label permutation also covers all 495 quadruples"
    return {
        "seed": result["seed"],
        "accepted_moves_replayed": accepted,
        "best_metrics": result["best_metrics"],
        "candidate_sha256": result["candidate"]["sha256"],
        "metamorphic_witness_check": metamorphic,
    }


def audit_control(manifest: dict[str, object]) -> dict[str, object]:
    binding = manifest["control_cover"]
    path = resolve(binding["path"])
    if digest(path) != binding["sha256"]:
        raise ValueError("control-cover hash mismatch")
    full = load_blocks(path, 41)
    full_missing = uncovered(full)
    if full_missing:
        raise ValueError("41-block positive control is not a cover")
    deleted = set(full)
    deleted.remove(min(deleted))
    deletion_missing = uncovered(deleted)
    if not deletion_missing:
        raise ValueError("one-block-deletion negative control unexpectedly covers")
    return {
        "positive_blocks": 41,
        "positive_covered_quadruples": 495,
        "deleted_blocks": 40,
        "deleted_uncovered_quadruples": len(deletion_missing),
    }


def audit(manifest_path: Path) -> dict[str, object]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if digest(resolve(manifest["source"]["path"])) != manifest["source"]["sha256"]:
        raise ValueError("manifest source hash mismatch")
    producer = resolve(manifest["producer"]["path"])
    checker = resolve(manifest["independent_checker"]["path"])
    if digest(producer) != manifest["producer"]["sha256"] or digest(checker) != manifest["independent_checker"]["sha256"]:
        raise ValueError("code hash mismatch")
    rows = []
    for binding in manifest["results"]:
        result_path = resolve(binding["path"])
        if digest(result_path) != binding["sha256"]:
            raise ValueError("result hash mismatch")
        rows.append(audit_seed(result_path))
    best = min(row["best_metrics"]["uncovered_quadruples"] for row in rows)
    expected = "WITNESS_CANDIDATE" if best == 0 else "NO_WITNESS"
    if manifest["status"] != expected:
        raise ValueError("manifest status mismatch")
    return {
        "schema_version": 1,
        "status": "valid",
        "screen_status": manifest["status"],
        "seeds_audited": len(rows),
        "best_uncovered_quadruples": best,
        "accepted_moves_replayed": sum(row["accepted_moves_replayed"] for row in rows),
        "control": audit_control(manifest),
        "runs": rows,
        "claim_limit": "The audit validates only the recorded heuristic screen and candidates; NO_WITNESS is not an exclusion.",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    receipt = audit(args.manifest)
    payload = json.dumps(receipt, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(payload, encoding="utf-8")
    print(json.dumps(receipt, sort_keys=True))


if __name__ == "__main__":
    main()

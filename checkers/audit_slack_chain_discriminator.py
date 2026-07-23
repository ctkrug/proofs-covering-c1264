#!/usr/bin/env python3
"""Independent direct replay for the four-exchange slack-chain discriminator.

This file deliberately does not import producer helpers.  It reconstructs all
blocks, quadruples, counters, token transitions, and subtrade tests directly.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import itertools
import json
import math
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
POINTS = tuple(range(12))
BLOCKS = list(itertools.combinations(POINTS, 6))
QUADS = list(itertools.combinations(POINTS, 4))
PAIRS = list(itertools.combinations(POINTS, 2))
BLOCK_INDEX = {block: index for index, block in enumerate(BLOCKS)}
QUAD_INDEX = {quad: index for index, quad in enumerate(QUADS)}
PAIR_INDEX = {pair: index for index, pair in enumerate(PAIRS)}


def resolve(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def load_candidate(path: Path, expected: int) -> set[int]:
    answer: list[int] = []
    for line_number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        block = tuple(int(value) - 1 for value in raw.split())
        if len(block) != 6 or block != tuple(sorted(set(block))) or block not in BLOCK_INDEX:
            raise ValueError(f"{path}:{line_number}: malformed block")
        answer.append(BLOCK_INDEX[block])
    if len(answer) != expected or len(set(answer)) != expected:
        raise ValueError(f"{path}: expected {expected} distinct blocks")
    return set(answer)


def direct_counts(selected: set[int]) -> tuple[list[int], list[int], list[int]]:
    # Independently reconstruct incidences from combinations rather than using
    # producer tables.  This is equivalent to the direct containment scan but
    # visits only the 15 quadruples and 15 pairs belonging to each block.
    quad_counts = [0] * len(QUADS)
    point_counts = [0] * len(POINTS)
    pair_counts = [0] * len(PAIRS)
    for index in selected:
        block = BLOCKS[index]
        for quad in itertools.combinations(block, 4):
            quad_counts[QUAD_INDEX[quad]] += 1
        for point in block:
            point_counts[point] += 1
        for pair in itertools.combinations(block, 2):
            pair_counts[PAIR_INDEX[pair]] += 1
    return quad_counts, point_counts, pair_counts


def metrics(selected: set[int]) -> dict[str, int]:
    quad_counts, point_counts, pair_counts = direct_counts(selected)
    return metrics_from_counts(quad_counts, point_counts, pair_counts)


def metrics_from_counts(
    quad_counts: list[int], point_counts: list[int], pair_counts: list[int]
) -> dict[str, int]:
    return {
        "uncovered_quadruples": sum(value == 0 for value in quad_counts),
        "point_degree_deviation": sum(abs(value - 20) for value in point_counts),
        "pair_deficit_below_9": sum(max(0, 9 - value) for value in pair_counts),
        "pair_excess_above_10": sum(max(0, value - 10) for value in pair_counts),
    }


def rank(value: dict[str, int]) -> tuple[int, int, int, int]:
    return (
        value["uncovered_quadruples"],
        value["pair_deficit_below_9"] + value["pair_excess_above_10"],
        value["pair_excess_above_10"],
        value["pair_deficit_below_9"],
    )


def energy(value: dict[str, int]) -> int:
    return 10_000 * value["uncovered_quadruples"] + 4 * value["pair_deficit_below_9"] + 8 * value["pair_excess_above_10"]


def signature(indices: tuple[int, ...]) -> tuple[int, ...]:
    return tuple(sum(point in BLOCKS[index] for index in indices) for point in POINTS)


def proper_subtrade(remove: tuple[int, ...], add: tuple[int, ...]) -> bool:
    for size in range(1, 4):
        removed = {signature(part) for part in itertools.combinations(remove, size)}
        if any(signature(part) in removed for part in itertools.combinations(add, size)):
            return True
    return False


def endpoint_hash(selected: set[int]) -> str:
    return hashlib.sha256((",".join(str(value) for value in sorted(selected)) + "\n").encode("ascii")).hexdigest()


def uncovered(selected: set[int]) -> set[tuple[int, ...]]:
    quad_counts, _, _ = direct_counts(selected)
    return {quad for quad, count in zip(QUADS, quad_counts) if count == 0}


def update_counts(
    quad_counts: list[int], point_counts: list[int], pair_counts: list[int], block_index: int, direction: int
) -> None:
    block = BLOCKS[block_index]
    for quad in itertools.combinations(block, 4):
        quad_counts[QUAD_INDEX[quad]] += direction
    for point in block:
        point_counts[point] += direction
    for pair in itertools.combinations(block, 2):
        pair_counts[PAIR_INDEX[pair]] += direction


def validate_chain_event(
    event: dict[str, object],
    selected: set[int],
    expected_complete_index: int,
    attempt_budget: int,
) -> tuple[set[int], dict[str, int]]:
    if event["complete_index"] != expected_complete_index:
        raise ValueError("nonconsecutive complete-chain index")
    attempt_index = int(event["attempt_index"])
    if not 1 <= attempt_index <= attempt_budget:
        raise ValueError("attempt index outside declared budget")
    cycle = tuple(event["cycle"])
    if len(cycle) != 4 or len(set(cycle)) != 4 or not set(cycle) <= set(POINTS):
        raise ValueError("cycle is not four distinct points")
    a, b, c, d = cycle
    edges = ((a, b), (b, c), (c, d), (d, a))
    steps = event["steps"]
    if len(steps) != 4:
        raise ValueError("chain does not have four exchanges")
    original = set(selected)
    working = set(selected)
    quad_counts, degree, pair_counts = direct_counts(original)
    start_missing = {quad for quad, count in zip(QUADS, quad_counts) if count == 0}
    before_metrics = metrics_from_counts(quad_counts, degree, pair_counts)
    removed: list[int] = []
    added: list[int] = []
    for position, (step, edge) in enumerate(zip(steps, edges), 1):
        old = int(step["remove"])
        new = int(step["add"])
        source = int(step["source"])
        target = int(step["target"])
        if (source, target) != edge:
            raise ValueError("wrong degree-token edge")
        if old not in working or new in working:
            raise ValueError("selected/unselected exchange membership failure")
        if old not in original or old in removed:
            raise ValueError("removal is not a distinct original block")
        if new in original or new in added or new in removed:
            raise ValueError("addition violates disjoint no-cancellation rule")
        old_block = set(BLOCKS[old])
        new_block = set(BLOCKS[new])
        if len(old_block & new_block) != 5:
            raise ValueError("exchange is not a one-point replacement")
        if source not in old_block or target in old_block or new_block != (old_block - {source}) | {target}:
            raise ValueError("exchange does not realize recorded token edge")
        working.remove(old)
        working.add(new)
        update_counts(quad_counts, degree, pair_counts, old, -1)
        update_counts(quad_counts, degree, pair_counts, new, 1)
        removed.append(old)
        added.append(new)
        expected = [20] * 12
        if position < 4:
            expected[a] = 19
            expected[cycle[position]] = 21
            if sum(abs(value - 20) for value in degree) != 2:
                raise ValueError("intermediate degree L1 is not two")
        if degree != expected:
            raise ValueError("intermediate/final degree vector is wrong")
    remove_tuple = tuple(removed)
    add_tuple = tuple(added)
    if event["remove"] != removed or event["add"] != added:
        raise ValueError("summary block IDs differ from step IDs")
    if len(working) != 40 or working == original or signature(remove_tuple) != signature(add_tuple):
        raise ValueError("endpoint is not a nontrivial exact-degree return")
    target_quad = tuple(event["target_quad"])
    if target_quad not in start_missing:
        raise ValueError("target was not missing at chain start")
    if not any(set(target_quad).issubset(BLOCKS[index]) for index in added):
        raise ValueError("no final addition covers the starting target")
    computed_subtrade = proper_subtrade(remove_tuple, add_tuple)
    if bool(event["proper_subtrade"]) != computed_subtrade:
        raise ValueError("proper-subtrade flag mismatch")
    endpoint_metrics = metrics_from_counts(quad_counts, degree, pair_counts)
    if event["endpoint_metrics"] != endpoint_metrics:
        raise ValueError("endpoint metrics mismatch")
    if event["endpoint_sha256"] != endpoint_hash(working):
        raise ValueError("endpoint hash mismatch")
    if event["before_metrics"] != before_metrics:
        raise ValueError("before metrics mismatch")
    fraction = (attempt_index - 1) / max(1, attempt_budget - 1)
    expected_temperature = 50_000.0 * ((100.0 / 50_000.0) ** fraction)
    if not math.isclose(float(event["temperature"]), expected_temperature, rel_tol=1e-12):
        raise ValueError("temperature schedule mismatch")
    delta = energy(endpoint_metrics) - energy(before_metrics)
    expected_threshold = 1.0 if delta <= 0 else math.exp(-delta / expected_temperature)
    if not math.isclose(float(event["acceptance_threshold"]), expected_threshold, rel_tol=1e-12, abs_tol=1e-300):
        raise ValueError("acceptance threshold mismatch")
    draw = float(event["acceptance_draw"])
    if not 0.0 <= draw < 1.0:
        raise ValueError("acceptance draw outside [0,1)")
    expected_accept = not computed_subtrade and draw < expected_threshold
    if bool(event["accepted"]) != expected_accept:
        raise ValueError("accept/reject decision mismatch")
    return working, endpoint_metrics


def mutation_controls(event: dict[str, object], selected: set[int], attempt_budget: int) -> dict[str, str]:
    controls = {}
    mutations = {}
    altered = copy.deepcopy(event)
    altered["steps"][0]["add"] = next(index for index in selected if index != altered["steps"][0]["remove"])
    mutations["altered_intermediate_degree_or_selected_addition"] = altered
    wrong_edge = copy.deepcopy(event)
    wrong_edge["steps"][1]["source"] = wrong_edge["cycle"][0]
    mutations["wrong_token_edge"] = wrong_edge
    fake_endpoint = copy.deepcopy(event)
    fake_endpoint["steps"][3]["add"] = fake_endpoint["steps"][0]["add"]
    mutations["fake_exact_endpoint"] = fake_endpoint
    selected_add = copy.deepcopy(event)
    selected_add["steps"][2]["add"] = next(index for index in selected if index != selected_add["steps"][2]["remove"])
    mutations["selected_addition"] = selected_add
    for name, mutated in mutations.items():
        try:
            validate_chain_event(mutated, set(selected), 1, attempt_budget)
        except ValueError:
            controls[name] = "rejected"
        else:
            raise ValueError(f"mutation control unexpectedly passed: {name}")
    return controls


def audit_seed(result_path: Path) -> tuple[dict[str, object], dict[str, object] | None]:
    result = json.loads(result_path.read_text(encoding="utf-8"))
    source_path = resolve(result["source"]["path"])
    if digest(source_path) != result["source"]["sha256"]:
        raise ValueError("source hash mismatch")
    selected = load_candidate(source_path, 40)
    if metrics(selected) != result["initial_metrics"]:
        raise ValueError("initial metrics mismatch")
    initial_selected = set(selected)
    best_selected = set(selected)
    best_metrics = metrics(selected)
    trace_path = resolve(result["trace"]["path"])
    if digest(trace_path) != result["trace"]["sha256"]:
        raise ValueError("trace hash mismatch")
    chain_hash = result["initial_chain_sha256"]
    complete = accepted = eligible = 0
    distinct: set[str] = set()
    target_histogram: Counter[str] = Counter()
    first_event = None
    for raw in trace_path.read_text(encoding="utf-8").splitlines():
        event = json.loads(raw)
        complete += 1
        if first_event is None:
            first_event = copy.deepcopy(event)
        endpoint, endpoint_metrics = validate_chain_event(event, selected, complete, result["attempt_budget"])
        target_histogram["-".join(str(point + 1) for point in event["target_quad"])] += 1
        distinct.add(event["endpoint_sha256"])
        if not event["proper_subtrade"]:
            eligible += 1
            if rank(endpoint_metrics) < rank(best_metrics):
                best_selected = set(endpoint)
                best_metrics = dict(endpoint_metrics)
        base = dict(event)
        recorded = base.pop("chain_sha256")
        chain_hash = hashlib.sha256((chain_hash + "\n" + canonical_json(base)).encode("utf-8")).hexdigest()
        if chain_hash != recorded:
            raise ValueError("trace hash chain mismatch")
        if event["accepted"]:
            selected = endpoint
            accepted += 1
    if complete != result["complete_chains"] or accepted != result["accepted_endpoints"]:
        raise ValueError("complete/accepted count mismatch")
    if eligible != result["eligible_indecomposable_endpoints"]:
        raise ValueError("eligible endpoint count mismatch")
    if chain_hash != result["final_chain_sha256"]:
        raise ValueError("final chain hash mismatch")
    if metrics(selected) != result["final_metrics"] or best_metrics != result["best_metrics"]:
        raise ValueError("final/best metric mismatch")
    if sum(result["failure_reasons"].values()) + complete != result["attempted_chains"]:
        raise ValueError("attempt accounting mismatch")
    if dict(sorted(target_histogram.items())) != result["target_histogram"] or len(distinct) != result["distinct_endpoint_hashes"]:
        raise ValueError("target or distinct-endpoint accounting mismatch")
    candidate_path = resolve(result["candidate"]["path"])
    if digest(candidate_path) != result["candidate"]["sha256"]:
        raise ValueError("candidate hash mismatch")
    candidate = load_candidate(candidate_path, 40)
    if candidate != best_selected or metrics(candidate) != best_metrics:
        raise ValueError("best candidate mismatch")
    status = "WITNESS_CANDIDATE" if best_metrics["uncovered_quadruples"] == 0 else "NO_WITNESS"
    if result["status"] != status:
        raise ValueError("status mismatch")
    return {
        "seed": result["seed"],
        "attempted_chains": result["attempted_chains"],
        "complete_chains_replayed": complete,
        "eligible_endpoints": eligible,
        "accepted_endpoints": accepted,
        "distinct_endpoint_hashes": len(distinct),
        "best_metrics": best_metrics,
        "candidate_sha256": result["candidate"]["sha256"],
    }, ({"event": first_event, "selected": initial_selected} if first_event else None)


def audit_control_cover(manifest: dict[str, object]) -> dict[str, int]:
    binding = manifest["control_cover"]
    path = resolve(binding["path"])
    if digest(path) != binding["sha256"]:
        raise ValueError("control cover hash mismatch")
    cover = load_candidate(path, 41)
    if uncovered(cover):
        raise ValueError("41-block positive control fails")
    deletion = set(cover)
    deletion.remove(min(deletion))
    missing = uncovered(deletion)
    if not missing:
        raise ValueError("one-block-deletion negative control fails")
    return {"positive_covered_quadruples": 495, "deletion_uncovered_quadruples": len(missing)}


def audit(manifest_path: Path, control_audit_path: Path) -> dict[str, object]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    bindings = ["source", "producer", "independent_checker", "frozen_control_producer", "frozen_control_checker", "control_manifest"]
    for name in bindings:
        binding = manifest[name]
        if digest(resolve(binding["path"])) != binding["sha256"]:
            raise ValueError(f"{name} hash mismatch")
    rows = []
    mutation_fixture = None
    for binding in manifest["treatment_results"]:
        path = resolve(binding["path"])
        if digest(path) != binding["sha256"]:
            raise ValueError("treatment result hash mismatch")
        row, fixture = audit_seed(path)
        rows.append(row)
        if mutation_fixture is None and fixture is not None:
            mutation_fixture = fixture
    if not rows:
        raise ValueError("no treatment rows")
    best = min(row["best_metrics"]["uncovered_quadruples"] for row in rows)
    expected_status = "PASS_SIGNAL" if best <= 5 else "STOP_SIGNAL"
    if manifest["status"] != expected_status:
        raise ValueError("manifest decision mismatch")
    total_complete = sum(row["complete_chains_replayed"] for row in rows)
    if total_complete < 20:
        expected_status = "STOP_SIGNAL"
    control_audit = json.loads(control_audit_path.read_text(encoding="utf-8"))
    if control_audit.get("status") != "valid":
        raise ValueError("frozen control audit is not valid")
    if [row["seed"] for row in control_audit["runs"]] != manifest["seeds_predeclared"]:
        raise ValueError("frozen control seeds differ")
    mutation_result = {}
    if mutation_fixture is not None:
        mutation_result = mutation_controls(
            mutation_fixture["event"], mutation_fixture["selected"], manifest["attempts_per_seed"]
        )
    receipt = {
        "schema_version": 1,
        "status": "valid",
        "discriminator_status": expected_status,
        "manifest": {"path": str(manifest_path), "sha256": digest(manifest_path)},
        "control_audit": {"path": str(control_audit_path), "sha256": digest(control_audit_path)},
        "treatment_runs": rows,
        "treatment_complete_chains": total_complete,
        "treatment_best_uncovered": best,
        "matched_control_best_uncovered": control_audit["best_uncovered_quadruples"],
        "matched_control_accepted_moves_replayed": control_audit["accepted_moves_replayed"],
        "direct_cover_controls": audit_control_cover(manifest),
        "mutation_controls": mutation_result,
        "claim_limit": "The receipt validates this fixed heuristic discriminator only; STOP_SIGNAL is not a lower bound or an exclusion of 40 blocks.",
    }
    return receipt


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--control-audit", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    receipt = audit(args.manifest, args.control_audit)
    payload = json.dumps(receipt, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(payload, encoding="utf-8")
    print(json.dumps(receipt, sort_keys=True))


if __name__ == "__main__":
    main()

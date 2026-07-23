#!/usr/bin/env python3
"""Fail-closed reconstruction, inventory, and proof audit for the C(11,5,3) hard tail.

This checker does not read the ignored parent CNFs.  It reconstructs the
ordinary-cover encoding from the semantic definition, regenerates the five
top-level and 42 third-level CNF hashes, independently rebuilds the 790
fourth-level orbit recipes, binds every measured row to its frozen protocol,
and replays every claimed UNSAT proof.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import itertools
import json
import math
import subprocess
import tempfile
from collections import Counter, deque
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]
POINTS = tuple(range(1, 12))
BLOCKS = tuple(itertools.combinations(POINTS, 5))
ROOT_BLOCK = (1, 2, 3, 4, 5)
ORDER = (4, 3, 2, 1, 0)
BASE = ROOT / "artifacts/classification/ordinary-c1153-v1"
FOURTH = BASE / "hard-tail-fourth-split"
CHECKER = ROOT / "toolchains/drat-trim/drat-trim"
NEGATIVE_CONTROL_LEAF = "intersection-4-third-04-fourth-014"


def sha_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text())


def read_cover(path: Path) -> tuple[tuple[int, ...], ...]:
    rows = tuple(sorted(tuple(sorted(map(int, line.split()))) for line in path.read_text().splitlines() if line.strip()))
    if len(rows) != 20 or len(set(rows)) != 20:
        raise ValueError("representative must contain 20 distinct blocks")
    covered = {triple for block in rows for triple in itertools.combinations(block, 3)}
    if covered != set(itertools.combinations(POINTS, 3)):
        raise ValueError("representative does not cover all triples")
    return rows


def permute_design(design: tuple[tuple[int, ...], ...], a: int, b: int) -> tuple[tuple[int, ...], ...]:
    def move(point: int) -> int:
        return b if point == a else a if point == b else point

    return tuple(sorted(tuple(sorted(move(point) for point in block)) for block in design))


def normalize_at_block(design: tuple[tuple[int, ...], ...], source: tuple[int, ...]) -> tuple[tuple[int, ...], ...]:
    outside = tuple(point for point in POINTS if point not in set(source))
    target_outside = tuple(point for point in POINTS if point not in set(ROOT_BLOCK))
    mapping = dict(zip(source, ROOT_BLOCK))
    mapping.update(zip(outside, target_outside))
    return tuple(sorted(tuple(sorted(mapping[point] for point in block)) for block in design))


def normalized_orbit(design: tuple[tuple[int, ...], ...]) -> set[tuple[tuple[int, ...], ...]]:
    seeds = {normalize_at_block(design, block) for block in design}
    queue = deque(seeds)
    seen = set(seeds)
    generators = tuple((point, point + 1) for point in range(1, 5)) + tuple((point, point + 1) for point in range(6, 11))
    while queue:
        current = queue.popleft()
        for left, right in generators:
            image = permute_design(current, left, right)
            if image not in seen:
                seen.add(image)
                queue.append(image)
    if len(seen) != 7200 or any(ROOT_BLOCK not in image for image in seen):
        raise ValueError("root-normalized representative orbit mismatch")
    return seen


def exact_twenty(primary: Iterable[int], top_id: int) -> tuple[list[list[int]], int]:
    clauses = [[top_id + 1], [-(top_id + 2)]]
    truth, falsity, next_variable = top_id + 1, top_id + 2, top_id + 3
    previous = [truth] + [falsity] * 21
    for variable in primary:
        current = [truth]
        for threshold in range(1, 22):
            state = next_variable
            next_variable += 1
            already, predecessor = previous[threshold], previous[threshold - 1]
            clauses.extend(
                [
                    [-already, state],
                    [-predecessor, -variable, state],
                    [-state, already, predecessor],
                    [-state, already, variable],
                ]
            )
            current.append(state)
        previous = current
    clauses.extend([[previous[20]], [-previous[21]]])
    return clauses, next_variable - 1


def cnf_bytes(clauses: Iterable[Iterable[int]], variables: int) -> bytes:
    materialized = [tuple(clause) for clause in clauses]
    lines = [f"p cnf {variables} {len(materialized)}\n"]
    lines.extend(" ".join(map(str, clause)) + " 0\n" for clause in materialized)
    return "".join(lines).encode("ascii")


def cell_actions(fixed: tuple[tuple[int, ...], ...]) -> list[dict[int, int]]:
    cells: dict[tuple[int, ...], tuple[int, ...]] = {}
    for point in POINTS:
        signature = tuple(index for index, block in enumerate(fixed) if point in block)
        cells.setdefault(signature, tuple())
        cells[signature] += (point,)
    ordered = [cells[key] for key in sorted(cells)]
    actions = []
    for targets in itertools.product(*(tuple(itertools.permutations(cell)) for cell in ordered)):
        action: dict[int, int] = {}
        for source, target in zip(ordered, targets):
            action.update(zip(source, target))
        actions.append(action)
    expected = math.prod(math.factorial(len(cell)) for cell in ordered)
    if len(actions) != expected:
        raise ValueError("cell-stabilizer enumeration mismatch")
    return actions


def ordered_orbits(
    eligible: set[tuple[int, ...]], actions: list[dict[int, int]]
) -> list[set[tuple[int, ...]]]:
    unseen = set(eligible)
    orbits = []
    while unseen:
        seed = min(unseen)
        orbit = {tuple(sorted(action[point] for point in seed)) for action in actions}
        if not orbit <= unseen:
            raise ValueError("orbit partition overlap")
        orbits.append(orbit)
        unseen -= orbit
    return orbits


def reconstruct_hierarchy() -> tuple[
    dict[str, bytes],
    dict[str, bytes],
    dict[str, tuple[dict[str, object], bytes]],
    dict[str, object],
]:
    top_manifest = read_json(BASE / "manifest.json")
    hard_manifest = read_json(BASE / "hard-split/manifest.json")
    fourth_manifest = read_json(FOURTH / "manifest.json")
    positions = {block: index for index, block in enumerate(BLOCKS, 1)}

    representative_path = ROOT / top_manifest["known_class_blocking"]["representative"]["path"]
    if sha(representative_path) != top_manifest["known_class_blocking"]["representative"]["sha256"]:
        raise ValueError("representative hash mismatch")
    representative = read_cover(representative_path)
    normalized = normalized_orbit(representative)
    normalized_indices = sorted(tuple(sorted(positions[block] for block in image)) for image in normalized)
    blockers = [[-variable for variable in image] for image in normalized_indices]
    coverage = [
        [positions[block] for block in BLOCKS if set(triple) <= set(block)]
        for triple in itertools.combinations(POINTS, 3)
    ]
    cardinality, variables = exact_twenty(range(1, 463), 462)
    if variables != 10166:
        raise ValueError("cardinality variable count mismatch")
    shared = coverage + cardinality + [[positions[ROOT_BLOCK]]] + blockers

    recorded_top = {leaf["id"]: leaf for leaf in top_manifest["leaves"]}
    top_bytes: dict[str, bytes] = {}
    top_tails: dict[str, list[list[int]]] = {}
    second_earlier: set[tuple[int, ...]] = set()
    for overlap in ORDER:
        leaf_id = f"intersection-{overlap}"
        orbit = {block for block in BLOCKS if block != ROOT_BLOCK and len(set(block) & set(ROOT_BLOCK)) == overlap}
        canonical = min(orbit)
        tail = [[-positions[block]] for block in sorted(second_earlier)] + [[positions[canonical]]]
        raw = cnf_bytes(shared + tail, variables)
        leaf = recorded_top[leaf_id]
        if sha_bytes(raw) != leaf["cnf"]["sha256"] or len(raw) != leaf["cnf"]["bytes"]:
            raise ValueError(f"{leaf_id}: regenerated top CNF mismatch")
        top_bytes[leaf_id] = raw
        top_tails[leaf_id] = tail
        second_earlier.update(orbit)

    hard_parents = {parent["id"]: parent for parent in hard_manifest["parents"]}
    third_bytes: dict[str, bytes] = {}
    third_tails: dict[str, list[list[int]]] = {}
    for parent_id, parent in hard_parents.items():
        second = tuple(parent["fixed_second_block"])
        actions = cell_actions((ROOT_BLOCK, second))
        if len(actions) != parent["stabilizer_order"]:
            raise ValueError(f"{parent_id}: third-level stabilizer mismatch")
        overlap = len(set(second) & set(ROOT_BLOCK))
        earlier_overlaps = ORDER[: ORDER.index(overlap)]
        excluded = {
            block
            for block in BLOCKS
            if block != ROOT_BLOCK and len(set(block) & set(ROOT_BLOCK)) in earlier_overlaps
        }
        orbits = ordered_orbits(set(BLOCKS) - excluded - {ROOT_BLOCK, second}, actions)
        if len(orbits) != parent["child_count"]:
            raise ValueError(f"{parent_id}: third-level branch count mismatch")
        earlier: set[tuple[int, ...]] = set()
        for child, orbit in zip(parent["children"], orbits):
            canonical = min(orbit)
            tail = [[-positions[block]] for block in sorted(earlier)] + [[positions[canonical]]]
            clauses = shared + top_tails[parent_id] + tail
            raw = cnf_bytes(clauses, variables)
            if (
                child["canonical_third_block"] != list(canonical)
                or sha_bytes(raw) != child["cnf"]["sha256"]
                or len(raw) != child["cnf"]["bytes"]
            ):
                raise ValueError(f"{child['id']}: regenerated third-level CNF mismatch")
            third_bytes[child["id"]] = raw
            third_tails[child["id"]] = top_tails[parent_id] + tail
            earlier.update(orbit)

    branch_index: dict[str, tuple[dict[str, object], bytes]] = {}
    parent_rows = []
    total_eligible = 0
    for parent in fourth_manifest["parents"]:
        parent_id = parent["id"]
        if parent_id not in third_bytes or sha_bytes(third_bytes[parent_id]) != parent["parent_cnf"]["sha256"]:
            raise ValueError(f"{parent_id}: fourth-level parent binding mismatch")
        fixed = tuple(tuple(block) for block in parent["fixed_blocks"])
        actions = cell_actions(fixed)
        if len(actions) != parent["stabilizer_order"]:
            raise ValueError(f"{parent_id}: fourth-level stabilizer mismatch")
        parent_clauses = shared + third_tails[parent_id]
        absent = {
            -clause[0]
            for clause in parent_clauses
            if len(clause) == 1 and -462 <= clause[0] < 0
        }
        eligible = set(BLOCKS) - {BLOCKS[variable - 1] for variable in absent} - set(fixed)
        orbits = ordered_orbits(eligible, actions)
        if len(orbits) != parent["branch_count"] or sum(map(len, orbits)) != parent["eligible_fourth_blocks"]:
            raise ValueError(f"{parent_id}: fourth-level partition count mismatch")
        earlier: set[tuple[int, ...]] = set()
        for branch, orbit in zip(parent["branches"], orbits):
            canonical = min(orbit)
            false_variables = [positions[block] for block in sorted(earlier)]
            assumptions = [-variable for variable in false_variables] + [positions[canonical]]
            recipe = (" ".join(map(str, assumptions)) + "\n").encode("ascii")
            if (
                branch["canonical_fourth_block"] != list(canonical)
                or branch["earlier_fourth_variables_forced_false"] != false_variables
                or branch["unit_recipe_sha256"] != sha_bytes(recipe)
            ):
                raise ValueError(f"{branch['id']}: fourth-level recipe mismatch")
            unit_lines = b"".join(f"{value} 0\n".encode("ascii") for value in assumptions)
            branch_index[branch["id"]] = (branch, unit_lines)
            earlier.update(orbit)
        total_eligible += len(eligible)
        parent_rows.append(
            {
                "id": parent_id,
                "parent_cnf_sha256": sha_bytes(third_bytes[parent_id]),
                "branches": len(orbits),
                "eligible_blocks": len(eligible),
                "stabilizer_order": len(actions),
            }
        )

    if len(branch_index) != fourth_manifest["total_branches"] or len(branch_index) != 790:
        raise ValueError("fourth-level global branch count mismatch")
    if total_eligible != 5246:
        raise ValueError("fourth-level eligible-block count mismatch")
    reconstruction = {
        "representative": {
            "path": str(representative_path.relative_to(ROOT)),
            "sha256": sha(representative_path),
            "covers_triples": 165,
            "root_normalized_images": len(normalized),
        },
        "top_level": {
            "count": len(top_bytes),
            "hashes": {key: sha_bytes(value) for key, value in sorted(top_bytes.items())},
        },
        "third_level": {
            "count": len(third_bytes),
            "hashes": {key: sha_bytes(value) for key, value in sorted(third_bytes.items())},
        },
        "fourth_level": {
            "parents": parent_rows,
            "parent_count": len(parent_rows),
            "branches": len(branch_index),
            "eligible_blocks": total_eligible,
        },
    }
    return top_bytes, third_bytes, branch_index, reconstruction


def protocol_rows() -> tuple[dict[str, tuple[str, dict[str, object]]], dict[str, str]]:
    campaign_rows: dict[str, tuple[str, dict[str, object]]] = {}
    bindings: dict[str, str] = {}
    specifications = (
        ("discriminator", "discriminator-10s-protocol.json", "discriminator-10s-summary.json"),
        ("boundary", "boundary-10s-protocol.json", "boundary-10s-summary.json"),
        ("suffix", "suffix-proof-scale-3s-protocol.json", "suffix-proof-scale-3s-summary.json"),
    )
    for label, protocol_name, summary_name in specifications:
        protocol_path = FOURTH / protocol_name
        summary_path = FOURTH / summary_name
        protocol = read_json(protocol_path)
        summary = read_json(summary_path)
        recorded = summary["protocol"]
        if recorded["sha256"] != sha(protocol_path) or ROOT / recorded["path"] != protocol_path:
            raise ValueError(f"{label}: summary-to-protocol binding mismatch")
        if label == "boundary":
            selected = [row["leaf_id"] for row in protocol["selection"]]
        else:
            selected = protocol["leaf_ids"]
        outcomes = {row["leaf_id"]: row for row in summary["outcomes"]}
        if len(outcomes) != len(summary["outcomes"]) or set(selected) != set(outcomes):
            raise ValueError(f"{label}: protocol and summary do not have a one-to-one leaf binding")
        for leaf_id in selected:
            if leaf_id in campaign_rows:
                raise ValueError(f"{leaf_id}: measured by more than one frozen protocol")
            campaign_rows[leaf_id] = (label, outcomes[leaf_id])
            bindings[summary_name] = sha(summary_path)
            bindings[protocol_name] = sha(protocol_path)
    return campaign_rows, bindings


def result_path(label: str, leaf_id: str) -> Path:
    campaign = "suffix-proof-scale-3s" if label == "suffix" else "discriminator-10s"
    return FOURTH / campaign / leaf_id / "result.json"


def child_cnf_bytes(parent_raw: bytes, unit_lines: bytes) -> bytes:
    header, body = parent_raw.split(b"\n", 1)
    fields = header.decode("ascii").split()
    variables, clauses = int(fields[2]), int(fields[3])
    added = unit_lines.count(b"\n")
    return f"p cnf {variables} {clauses + added}\n".encode("ascii") + body + unit_lines


def replay_one(
    label: str,
    summary_row: dict[str, object],
    branch: dict[str, object],
    parent_raw: bytes,
    unit_lines: bytes,
    temporary: Path,
) -> dict[str, object]:
    leaf_id = branch["id"]
    path = result_path(label, leaf_id)
    result = read_json(path)
    if result != summary_row:
        raise ValueError(f"{leaf_id}: result file differs from its frozen summary row")
    expected = child_cnf_bytes(parent_raw, unit_lines)
    if sha_bytes(expected) != result["exact_cnf_sha256"]:
        raise ValueError(f"{leaf_id}: exact CNF hash mismatch")
    common = {
        "id": leaf_id,
        "protocol": label,
        "result_path": str(path.relative_to(ROOT)),
        "result_sha256": sha(path),
        "exact_cnf_sha256": result["exact_cnf_sha256"],
    }
    if result["status"] == "FIXED_CAP_TIMEOUT":
        return {**common, "status": "FIXED_CAP_TIMEOUT"}
    if result["status"] != "UNSAT_VERIFIED":
        raise ValueError(f"{leaf_id}: unsupported measured status {result['status']}")
    proof_path = ROOT / result["proof"]["path"]
    if sha(proof_path) != result["proof"]["sha256"]:
        raise ValueError(f"{leaf_id}: compressed proof hash mismatch")
    folder = temporary / leaf_id
    folder.mkdir()
    cnf_path = folder / "instance.cnf"
    proof_raw = folder / "proof.drat"
    cnf_path.write_bytes(expected)
    with gzip.open(proof_path, "rb") as source, proof_raw.open("wb") as target:
        while chunk := source.read(1024 * 1024):
            target.write(chunk)
    if sha(proof_raw) != result["proof"]["uncompressed_sha256"]:
        raise ValueError(f"{leaf_id}: uncompressed proof hash mismatch")
    completed = subprocess.run(
        [str(CHECKER), str(cnf_path), str(proof_raw)],
        capture_output=True,
        text=True,
        timeout=120,
    )
    transcript = completed.stdout + completed.stderr
    if completed.returncode != 0 or "VERIFIED" not in transcript:
        raise ValueError(f"{leaf_id}: DRAT replay failed")
    return {
        **common,
        "status": "UNSAT_REPLAYED",
        "proof_path": str(proof_path.relative_to(ROOT)),
        "proof_sha256": result["proof"]["sha256"],
    }


def negative_control(
    measured: dict[str, tuple[str, dict[str, object]]],
    branch_index: dict[str, tuple[dict[str, object], bytes]],
    parent_raw: bytes,
    temporary: Path,
) -> dict[str, object]:
    label, result = measured[NEGATIVE_CONTROL_LEAF]
    branch, unit_lines = branch_index[NEGATIVE_CONTROL_LEAF]
    exact = child_cnf_bytes(parent_raw, unit_lines)
    lines = unit_lines.splitlines(keepends=True)
    if not lines:
        raise ValueError("negative control has no units to alter")
    altered = child_cnf_bytes(parent_raw, b"".join(lines[:-1]))
    if sha_bytes(altered) == result["exact_cnf_sha256"]:
        raise ValueError("negative control did not alter the exact CNF hash")
    proof_path = ROOT / result["proof"]["path"]
    folder = temporary / "negative-control"
    folder.mkdir()
    cnf_path = folder / "altered.cnf"
    proof_raw = folder / "proof.drat"
    cnf_path.write_bytes(altered)
    with gzip.open(proof_path, "rb") as source, proof_raw.open("wb") as target:
        while chunk := source.read(1024 * 1024):
            target.write(chunk)
    completed = subprocess.run(
        [str(CHECKER), str(cnf_path), str(proof_raw)],
        capture_output=True,
        text=True,
        timeout=120,
    )
    if completed.returncode == 0:
        raise ValueError("altered-unit negative control unexpectedly verified")
    return {
        "leaf_id": NEGATIVE_CONTROL_LEAF,
        "alteration": "removed the canonical positive fourth-block unit",
        "recorded_exact_cnf_sha256": result["exact_cnf_sha256"],
        "altered_exact_cnf_sha256": sha_bytes(altered),
        "hash_mismatch_detected": sha_bytes(altered) != result["exact_cnf_sha256"],
        "checker_returncode": completed.returncode,
        "proof_replay_rejected": True,
        "unaltered_exact_cnf_sha256": sha_bytes(exact),
    }


def audit(workers: int) -> dict[str, object]:
    if workers < 1 or workers > 4:
        raise ValueError("workers must be between 1 and 4")
    if not CHECKER.is_file():
        raise ValueError("pinned drat-trim checker is missing")
    top_bytes, third_bytes, branch_index, reconstruction = reconstruct_hierarchy()
    del top_bytes
    measured, bindings = protocol_rows()
    all_ids = set(branch_index)
    if not set(measured) <= all_ids:
        raise ValueError("a measured leaf is absent from the 790-branch partition")
    if len(measured) != 438:
        raise ValueError("measured leaf count mismatch")

    fourth_manifest = read_json(FOURTH / "manifest.json")
    parent_by_leaf: dict[str, str] = {
        branch["id"]: parent["id"]
        for parent in fourth_manifest["parents"]
        for branch in parent["branches"]
    }
    rows = []
    with tempfile.TemporaryDirectory(prefix="ordinary-c1153-full-audit-") as raw_temporary:
        temporary = Path(raw_temporary)
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = []
            for leaf_id, (label, summary_row) in measured.items():
                branch, unit_lines = branch_index[leaf_id]
                parent_raw = third_bytes[parent_by_leaf[leaf_id]]
                futures.append(
                    pool.submit(
                        replay_one,
                        label,
                        summary_row,
                        branch,
                        parent_raw,
                        unit_lines,
                        temporary,
                    )
                )
            for future in as_completed(futures):
                rows.append(future.result())
        control_parent = third_bytes[parent_by_leaf[NEGATIVE_CONTROL_LEAF]]
        control = negative_control(measured, branch_index, control_parent, temporary)

    rows.sort(key=lambda row: row["id"])
    counts = Counter(row["status"] for row in rows)
    unmeasured = sorted(all_ids - set(measured))
    inventory = []
    measured_by_id = {row["id"]: row for row in rows}
    for leaf_id in sorted(all_ids):
        if leaf_id in measured_by_id:
            row = measured_by_id[leaf_id]
            inventory.append(
                {
                    "id": leaf_id,
                    "status": row["status"],
                    "protocol": row["protocol"],
                    "result_path": row["result_path"],
                    "result_sha256": row["result_sha256"],
                }
            )
        else:
            inventory.append({"id": leaf_id, "status": "UNMEASURED"})
    inventory_counts = Counter(row["status"] for row in inventory)
    expected_counts = {
        "UNSAT_REPLAYED": 406,
        "FIXED_CAP_TIMEOUT": 32,
        "UNMEASURED": 352,
    }
    if dict(inventory_counts) != expected_counts:
        raise ValueError(f"inventory accounting mismatch: {dict(inventory_counts)}")
    if len(unmeasured) + counts["FIXED_CAP_TIMEOUT"] != 384:
        raise ValueError("open-branch accounting mismatch")

    return {
        "schema_version": 1,
        "status": "VALID",
        "claim": "The compact 13-parent fourth-level partition has 790 branches: 406 independently replayed UNSAT, 32 measured timeouts, and 352 unmeasured; therefore 384 branches remain open.",
        "claim_limit": "This audit validates a scoped ordinary C(11,5,3) classification frontier. It does not prove ordinary-cover uniqueness and does not determine C(12,6,4).",
        "checker": {
            "path": str(CHECKER.relative_to(ROOT)),
            "sha256": sha(CHECKER),
            "source_path": "toolchains/drat-trim/drat-trim.c",
            "source_sha256": sha(ROOT / "toolchains/drat-trim/drat-trim.c"),
        },
        "bindings": {
            "top_manifest_sha256": sha(BASE / "manifest.json"),
            "hard_manifest_sha256": sha(BASE / "hard-split/manifest.json"),
            "fourth_manifest_sha256": sha(FOURTH / "manifest.json"),
            "protocol_and_summary_sha256": dict(sorted(bindings.items())),
        },
        "reconstruction": reconstruction,
        "accounting": {
            "partition_branches": len(all_ids),
            "measured_unique_branches": len(measured),
            "unsat_replayed": counts["UNSAT_REPLAYED"],
            "fixed_cap_timeouts": counts["FIXED_CAP_TIMEOUT"],
            "unmeasured": len(unmeasured),
            "open_branches": len(unmeasured) + counts["FIXED_CAP_TIMEOUT"],
            "previous_416_open_statement": "REJECTED_BY_EXACT_INVENTORY",
        },
        "search_efficiency": {
            "eligible_labelled_fourth_blocks_across_13_parents": 5246,
            "canonical_first_present_orbit_branches": 790,
            "eliminated_by_stabilizer_quotient": 4456,
            "reduction_percent": 84.94090735722455,
            "representation": "13 regenerated parent CNFs plus unit recipes; no materialized child-CNF portfolio",
        },
        "negative_control": control,
        "inventory": inventory,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    result = audit(args.workers)
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        output = args.output if args.output.is_absolute() else ROOT / args.output
        output.parent.mkdir(parents=True, exist_ok=False)
        output.write_text(rendered)
    print(rendered, end="")


if __name__ == "__main__":
    main()

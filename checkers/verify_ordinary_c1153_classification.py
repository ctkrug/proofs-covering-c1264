#!/usr/bin/env python3
"""Independent verifier for the unrestricted ordinary C(11,5,3) gate."""

from __future__ import annotations

import hashlib
import itertools
import json
import subprocess
from collections import deque
from pathlib import Path

from pysat.formula import CNF


ROOT = Path(__file__).resolve().parents[1]
POINTS = tuple(range(1, 12))
BLOCKS = tuple(itertools.combinations(POINTS, 5))
ROOT_BLOCK = (1, 2, 3, 4, 5)
ORDER = (4, 3, 2, 1, 0)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def clause_sha(clauses: list[list[int]]) -> str:
    raw = "".join(" ".join(map(str, row)) + " 0\n" for row in clauses)
    return hashlib.sha256(raw.encode("ascii")).hexdigest()


def read_cover(path: Path) -> tuple[tuple[int, ...], ...]:
    rows = tuple(sorted(tuple(sorted(map(int, line.split()))) for line in path.read_text().splitlines() if line.strip()))
    if len(rows) != 20 or len(set(rows)) != 20:
        raise ValueError("bad representative size")
    covered = {t for block in rows for t in itertools.combinations(block, 3)}
    if covered != set(itertools.combinations(POINTS, 3)):
        raise ValueError("representative misses a triple")
    return rows


def independent_cardinality(primary: list[int], top_id: int) -> tuple[list[list[int]], int]:
    clauses = [[top_id + 1], [-(top_id + 2)]]
    truth, falsity, next_var = top_id + 1, top_id + 2, top_id + 3
    prior = [truth] + [falsity] * 21
    for x in primary:
        current = [truth]
        for threshold in range(1, 22):
            y = next_var
            next_var += 1
            already, predecessor = prior[threshold], prior[threshold - 1]
            clauses += [[-already, y], [-predecessor, -x, y], [-y, already, predecessor], [-y, already, x]]
            current.append(y)
        prior = current
    clauses += [[prior[20]], [-prior[21]]]
    return clauses, next_var - 1


def permute_design(design: tuple[tuple[int, ...], ...], a: int, b: int) -> tuple[tuple[int, ...], ...]:
    def move(point: int) -> int:
        return b if point == a else a if point == b else point
    return tuple(sorted(tuple(sorted(move(p) for p in block)) for block in design))


def normalize_at_block(design: tuple[tuple[int, ...], ...], source_block: tuple[int, ...]) -> tuple[tuple[int, ...], ...]:
    source_set = set(source_block)
    source_complement = tuple(p for p in POINTS if p not in source_set)
    target_complement = tuple(p for p in POINTS if p not in set(ROOT_BLOCK))
    mapping = dict(zip(source_block, ROOT_BLOCK))
    mapping.update(zip(source_complement, target_complement))
    return tuple(sorted(tuple(sorted(mapping[p] for p in block)) for block in design))


def normalized_orbit_bfs(seed_design: tuple[tuple[int, ...], ...]) -> set[tuple[tuple[int, ...], ...]]:
    seeds = {normalize_at_block(seed_design, block) for block in seed_design}
    seen = set(seeds)
    queue = deque(seeds)
    generators = tuple((point, point + 1) for point in range(1, 5)) + tuple((point, point + 1) for point in range(6, 11))
    while queue:
        design = queue.popleft()
        for a, b in generators:
            image = permute_design(design, a, b)
            if image not in seen:
                seen.add(image)
                queue.append(image)
    if any(ROOT_BLOCK not in design for design in seen):
        raise ValueError("root stabilizer closure escaped the root")
    return seen


def validate_witness(path: Path) -> tuple[tuple[int, ...], ...]:
    return read_cover(path)


def verify(manifest_path: Path, replay: bool = False) -> dict[str, object]:
    manifest = json.loads(manifest_path.read_text())
    if manifest["unrestricted_domain"]["extra_degree_or_matching_assumptions"] is not False:
        raise ValueError("domain is restricted")
    representative_path = ROOT / manifest["known_class_blocking"]["representative"]["path"]
    if sha(representative_path) != manifest["known_class_blocking"]["representative"]["sha256"]:
        raise ValueError("representative hash mismatch")
    representative = read_cover(representative_path)

    normalized = normalized_orbit_bfs(representative)
    if len(normalized) != 7200:
        raise ValueError("root-normalized known orbit count mismatch")
    full_orbit_size = len(normalized) * len(BLOCKS) // 20
    if full_orbit_size != 166320 or 39916800 // full_orbit_size != 240:
        raise ValueError("orbit-incidence/automorphism count mismatch")
    positions = {block: i for i, block in enumerate(BLOCKS, 1)}
    normalized_indices = sorted(tuple(sorted(positions[block] for block in design)) for design in normalized)
    expected_blockers = [[-value for value in image] for image in normalized_indices]
    if clause_sha(expected_blockers) != manifest["core"]["known_image_blocker_sha256"]:
        raise ValueError("known-class blocker mismatch")

    coverage = [[positions[b] for b in BLOCKS if set(t) <= set(b)] for t in itertools.combinations(POINTS, 3)]
    cardinality, top = independent_cardinality(list(range(1, 463)), 462)
    if clause_sha(coverage) != manifest["core"]["coverage_clause_sha256"]:
        raise ValueError("coverage digest mismatch")
    if clause_sha(cardinality) != manifest["core"]["cardinality_clause_sha256"]:
        raise ValueError("cardinality recurrence mismatch")
    blocker_path = ROOT / manifest["known_class_blocking"]["reusable_blocker"]["path"]
    if sha(blocker_path) != manifest["known_class_blocking"]["reusable_blocker"]["sha256"]:
        raise ValueError("cached blocker hash mismatch")
    if CNF(from_file=str(blocker_path)).clauses != expected_blockers:
        raise ValueError("cached blocker reconstruction failed")
    base_path = ROOT / manifest["shared_normalized_base"]["path"]
    if sha(base_path) != manifest["shared_normalized_base"]["sha256"]:
        raise ValueError("shared base hash mismatch")
    if CNF(from_file=str(base_path)).clauses != coverage + cardinality + [[positions[ROOT_BLOCK]]] + expected_blockers:
        raise ValueError("shared base reconstruction failed")

    orbit_sets = {overlap: {b for b in BLOCKS if b != ROOT_BLOCK and len(set(b) & set(ROOT_BLOCK)) == overlap} for overlap in ORDER}
    if set().union(*orbit_sets.values()) != set(BLOCKS) - {ROOT_BLOCK} or sum(map(len, orbit_sets.values())) != 461:
        raise ValueError("second-block partition incomplete")

    earlier: set[tuple[int, ...]] = set()
    statuses = {}
    for leaf in manifest["leaves"]:
        overlap = int(leaf["minimum_present_second_block_intersection"])
        canonical = min(orbit_sets[overlap])
        branch = [[-positions[b]] for b in sorted(earlier)] + [[positions[canonical]]]
        expected = coverage + cardinality + [[positions[ROOT_BLOCK]]] + expected_blockers + branch
        cnf_path = ROOT / leaf["cnf"]["path"]
        if sha(cnf_path) != leaf["cnf"]["sha256"]:
            raise ValueError(f"{leaf['id']}: CNF hash mismatch")
        actual = CNF(from_file=str(cnf_path))
        if actual.nv != top or actual.clauses != expected:
            raise ValueError(f"{leaf['id']}: exact CNF reconstruction failed")
        result_path = ROOT / leaf["result"]["path"]
        result = json.loads(result_path.read_text())
        status = result["status"]
        statuses[leaf["id"]] = status
        if status == "SAT":
            witness = ROOT / result["witness"]["path"]
            if sha(witness) != result["witness"]["sha256"]:
                raise ValueError("witness hash mismatch")
            design = validate_witness(witness)
            if any(normalize_at_block(design, block) in normalized for block in design):
                raise ValueError("SAT witness belongs to blocked known class")
        elif status == "UNSAT_VERIFIED":
            proof = ROOT / result["proof"]["path"]
            if sha(proof) != result["proof"]["sha256"]:
                raise ValueError("proof hash mismatch")
            if replay:
                local_checker = ROOT / ".venv/sat-audit-tools/drat-trim/drat-trim"
                checker = local_checker if local_checker.exists() else ROOT / "toolchains/drat-trim/drat-trim"
                completed = subprocess.run([str(checker), str(cnf_path), str(proof)], capture_output=True, text=True)
                if completed.returncode != 0 or "VERIFIED" not in completed.stdout + completed.stderr:
                    raise ValueError("external proof replay failed")
        elif status != "NOT_RUN":
            raise ValueError(f"unsupported status {status}")
        earlier.update(orbit_sets[overlap])

    return {
        "schema_version": 1,
        "status": "VALID_FIRST_GATE",
        "unrestricted_domain": "verified",
        "full_known_orbit_size": full_orbit_size,
        "automorphism_order": 240,
        "root_normalized_known_images": len(normalized),
        "branch_leaf_count": 5,
        "branch_partition_coverage": 461,
        "exact_cnf_reconstructions": 5,
        "leaf_statuses": statuses,
        "classification_complete": all(value == "UNSAT_VERIFIED" for value in statuses.values()),
        "claim_limit": "The partition and exact instances are independently verified; the classification is incomplete until all leaves carry replay-verified certificates.",
    }


if __name__ == "__main__":
    path = ROOT / "artifacts/classification/ordinary-c1153-v1/manifest.json"
    print(json.dumps(verify(path), indent=2, sort_keys=True))

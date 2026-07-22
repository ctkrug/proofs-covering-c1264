#!/usr/bin/env python3
"""Build the bounded first gate for an unrestricted C(11,5,3)=20 classification.

No solver is run here.  The five leaves form a complete normalized partition;
UNSAT proofs are deliberately a later gate.
"""

from __future__ import annotations

import hashlib
import itertools
import json
from pathlib import Path

from pysat.formula import CNF


ROOT = Path(__file__).resolve().parents[1]
POINTS = tuple(range(1, 12))
BLOCKS = tuple(itertools.combinations(POINTS, 5))
ROOT_BLOCK = (1, 2, 3, 4, 5)
INTERSECTION_ORDER = (4, 3, 2, 1, 0)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def clause_sha(clauses: list[list[int]]) -> str:
    payload = "".join(" ".join(map(str, row)) + " 0\n" for row in clauses)
    return hashlib.sha256(payload.encode("ascii")).hexdigest()


def read_cover(path: Path) -> tuple[tuple[int, ...], ...]:
    cover = tuple(sorted(tuple(sorted(map(int, line.split()))) for line in path.read_text().splitlines() if line.strip()))
    if len(cover) != 20 or len(set(cover)) != 20:
        raise ValueError("representative must contain 20 distinct blocks")
    if any(len(block) != 5 or not set(block) <= set(POINTS) for block in cover):
        raise ValueError("invalid representative block")
    covered = {triple for block in cover for triple in itertools.combinations(block, 3)}
    if covered != set(itertools.combinations(POINTS, 3)):
        raise ValueError("representative is not a C(11,5,3) cover")
    return cover


def image_indices(cover: tuple[tuple[int, ...], ...], mapping: dict[int, int], positions: dict[tuple[int, ...], int]) -> tuple[int, ...]:
    return tuple(sorted(positions[tuple(sorted(mapping[p] for p in block))] for block in cover))


def normalized_seed(cover: tuple[tuple[int, ...], ...], source_block: tuple[int, ...], positions: dict[tuple[int, ...], int]) -> tuple[int, ...]:
    source_set = set(source_block)
    source_complement = tuple(p for p in POINTS if p not in source_set)
    target_complement = tuple(p for p in POINTS if p not in set(ROOT_BLOCK))
    mapping = dict(zip(source_block, ROOT_BLOCK))
    mapping.update(zip(source_complement, target_complement))
    return image_indices(cover, mapping, positions)


def known_images_containing_root(cover: tuple[tuple[int, ...], ...], positions: dict[tuple[int, ...], int]) -> set[tuple[int, ...]]:
    """Generate only the distinct stabilizer orbits of block-normalized seeds."""
    root_complement = tuple(p for p in POINTS if p not in set(ROOT_BLOCK))
    images: set[tuple[int, ...]] = set()
    seed_orbits = 0
    for source_block in cover:
        seed = normalized_seed(cover, source_block, positions)
        if seed in images:
            continue
        seed_orbits += 1
        for inside in itertools.permutations(ROOT_BLOCK):
            inside_map = dict(zip(ROOT_BLOCK, inside))
            for outside in itertools.permutations(root_complement):
                mapping = dict(inside_map)
                mapping.update(zip(root_complement, outside))
                image = tuple(sorted(positions[tuple(sorted(mapping[p] for p in BLOCKS[value - 1]))] for value in seed))
                images.add(image)
    root_variable = positions[ROOT_BLOCK]
    if any(root_variable not in image for image in images):
        raise AssertionError("root-normalized orbit generation escaped the root")
    if len(images) != 7200:
        raise AssertionError("maintained representative does not have the expected root-stabilizer orbit")
    for source_block in cover:
        if normalized_seed(cover, source_block, positions) not in images:
            raise AssertionError("a source-block normalization lies outside the generated orbit")
    if seed_orbits < 1:
        raise AssertionError("no normalized seed orbit generated")
    return images


def exact_count_twenty(primary: list[int], top_id: int) -> tuple[list[list[int]], int, dict[str, int]]:
    """DP equivalence: s(i,j) iff at least j of x[1..i] are true."""
    clauses: list[list[int]] = []
    true_var, false_var = top_id + 1, top_id + 2
    clauses.extend([[true_var], [-false_var]])
    next_var = false_var + 1
    previous = {0: true_var, **{j: false_var for j in range(1, 22)}}
    for literal in primary:
        current = {0: true_var}
        for j in range(1, 22):
            y = next_var
            next_var += 1
            a, b = previous[j], previous[j - 1]
            # y <-> a OR (b AND literal)
            clauses.extend([
                [-a, y],
                [-b, -literal, y],
                [-y, a, b],
                [-y, a, literal],
            ])
            current[j] = y
        previous = current
    clauses.extend([[previous[20]], [-previous[21]]])
    return clauses, next_var - 1, {
        "true_constant": true_var,
        "false_constant": false_var,
        "first_state_variable": false_var + 1,
        "last_state_variable": next_var - 1,
    }


def build(output: Path, representative_path: Path) -> dict[str, object]:
    output.mkdir(parents=True, exist_ok=False)
    cover = read_cover(representative_path)
    positions = {block: index for index, block in enumerate(BLOCKS, 1)}

    coverage = [
        [positions[block] for block in BLOCKS if set(triple) <= set(block)]
        for triple in itertools.combinations(POINTS, 3)
    ]
    cardinality, top, cardinality_meta = exact_count_twenty(list(range(1, 463)), 462)
    known_images = known_images_containing_root(cover, positions)
    blockers = [[-value for value in image] for image in sorted(known_images)]
    root_clause = [[positions[ROOT_BLOCK]]]
    blocker_path = output / "known-class-root-blocker.cnf"
    CNF(from_clauses=blockers).to_file(str(blocker_path))
    base_clauses = coverage + cardinality + root_clause + blockers
    base_path = output / "normalized-base.cnf"
    CNF(from_clauses=base_clauses).to_file(str(base_path))

    second_orbits = {
        overlap: tuple(block for block in BLOCKS if block != ROOT_BLOCK and len(set(block) & set(ROOT_BLOCK)) == overlap)
        for overlap in INTERSECTION_ORDER
    }
    if set().union(*(set(values) for values in second_orbits.values())) != set(BLOCKS) - {ROOT_BLOCK}:
        raise AssertionError("second-block orbits do not partition the remaining blocks")

    leaves = []
    earlier: set[tuple[int, ...]] = set()
    for ordinal, overlap in enumerate(INTERSECTION_ORDER, 1):
        orbit = second_orbits[overlap]
        canonical = min(orbit)
        branch = [[-positions[block]] for block in sorted(earlier)] + [[positions[canonical]]]
        clauses = coverage + cardinality + root_clause + blockers + branch
        cnf = CNF(from_clauses=clauses)
        if cnf.nv != top:
            raise AssertionError("unexpected variable range")
        leaf_id = f"intersection-{overlap}"
        folder = output / leaf_id
        folder.mkdir()
        cnf_path = folder / "instance.cnf"
        cnf.to_file(str(cnf_path))
        result_path = folder / "result.json"
        result_path.write_text(json.dumps({
            "schema_version": 1,
            "status": "NOT_RUN",
            "claim_limit": "No classification claim until this exact CNF has a replay-verified UNSAT proof or a directly validated SAT witness.",
        }, indent=2, sort_keys=True) + "\n")
        leaves.append({
            "id": leaf_id,
            "minimum_present_second_block_intersection": overlap,
            "canonical_second_block": list(canonical),
            "canonical_second_block_variable": positions[canonical],
            "earlier_orbit_variables_forced_false": len(earlier),
            "second_block_orbit_size": len(orbit),
            "cnf": {"path": str(cnf_path.relative_to(ROOT)), "sha256": sha(cnf_path), "bytes": cnf_path.stat().st_size, "variables": cnf.nv, "clauses": len(cnf.clauses)},
            "result": {"path": str(result_path.relative_to(ROOT)), "sha256": sha(result_path)},
        })
        earlier.update(orbit)

    manifest = {
        "schema_version": 1,
        "status": "BUILT_NOT_SOLVED",
        "theorem_target": "Every 20-block C(11,5,3) cover is isomorphic under S_11 to the maintained representative.",
        "unrestricted_domain": {
            "points": list(POINTS),
            "candidate_blocks": len(BLOCKS),
            "selected_blocks_exactly": 20,
            "covered_triples": 165,
            "extra_degree_or_matching_assumptions": False,
        },
        "normalization": {
            "root_block": list(ROOT_BLOCK),
            "argument": "Every object has a selected block and S_11 is transitive on 5-subsets, so some relabeling contains the fixed root block.",
            "root_stabilizer": "S_5 x S_6",
            "root_stabilizer_order": 86400,
        },
        "known_class_blocking": {
            "representative": {"path": str(representative_path.relative_to(ROOT)), "sha256": sha(representative_path)},
            "root_normalized_images": len(known_images),
            "expected_full_orbit_size": 166320,
            "expected_automorphism_order": 240,
            "reusable_blocker": {"path": str(blocker_path.relative_to(ROOT)), "sha256": sha(blocker_path), "bytes": blocker_path.stat().st_size},
            "argument": "With exactly 20 selected blocks, one negative 20-literal clause per root-normalized image excludes exactly that known isomorphism class.",
        },
        "shared_normalized_base": {"path": str(base_path.relative_to(ROOT)), "sha256": sha(base_path), "bytes": base_path.stat().st_size, "variables": top, "clauses": len(base_clauses)},
        "partition": {
            "kind": "least-present second-block orbit under the root stabilizer",
            "intersection_order": list(INTERSECTION_ORDER),
            "leaf_count": len(leaves),
            "coverage_argument": "The other 19 blocks occupy one of five stabilizer orbits. Choose the first nonempty orbit; the stabilizer maps one member to its canonical representative while preserving all earlier-orbit absences.",
        },
        "core": {
            "coverage_clause_count": len(coverage),
            "coverage_clause_sha256": clause_sha(coverage),
            "cardinality_clause_count": len(cardinality),
            "cardinality_clause_sha256": clause_sha(cardinality),
            "cardinality_semantics": "DP equivalence s(i,j) iff at least j of the first i primary variables are true; assert s(462,20) and not s(462,21).",
            "cardinality_variables": cardinality_meta,
            "known_image_blocker_count": len(blockers),
            "known_image_blocker_sha256": clause_sha(blockers),
        },
        "leaves": leaves,
        "completion_standard": "All five exact leaves must be replay-verified UNSAT, or every SAT leaf must be exhaustively enumerated and all witnesses canonicalized to the maintained class. A single validated nonisomorphic SAT witness disproves uniqueness.",
        "claim_limit": "This manifest and its CNFs are a candidate completeness partition. They become a classification theorem only after independent reconstruction/coverage audit and completed certificate verification.",
    }
    manifest_path = output / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return manifest


if __name__ == "__main__":
    target = ROOT / "artifacts/classification/ordinary-c1153-v1"
    representative = ROOT / "artifacts/prior-art/c1153-ljcr-cover.txt"
    print(json.dumps(build(target, representative), sort_keys=True))

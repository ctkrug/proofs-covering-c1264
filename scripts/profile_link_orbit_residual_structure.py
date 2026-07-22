#!/usr/bin/env python3
"""Compare structural residual signatures of validated exact-degree link orbits."""

from __future__ import annotations

import argparse
import collections
import hashlib
import itertools
import json
from pathlib import Path

from analyze_link_orbit import group_maps, image, load_link


MATCHING_WITHOUT_FIXED_POINT = {(2, 3), (4, 5), (6, 7), (8, 9), (10, 11)}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def profile(catalog_path: Path, core_path: Path | None = None) -> dict[str, object]:
    catalog = json.loads(catalog_path.read_text())
    rows = []
    invariant_images_checked = 0
    for index, orbit in enumerate(catalog["orbits"], 1):
        source = Path(orbit["source"]["path"])
        blocks = [tuple(map(int, line.split())) for line in source.read_text().splitlines() if line.strip()]
        pair_multiplicity = {
            pair: sum(set(pair) <= set(block) for block in blocks)
            for pair in itertools.combinations(range(1, 12), 2)
        }
        low_pairs = {pair for pair, value in pair_multiplicity.items() if value == 3}
        low_degrees = sorted(sum(point in pair for pair in low_pairs) for point in range(1, 12))
        low_triangles = sum(
            all(tuple(sorted(pair)) in low_pairs for pair in ((a, b), (a, c), (b, c)))
            for a, b, c in itertools.combinations(range(1, 12), 3)
        )
        orbit_blocks = load_link(source)
        image_alignment_counts = set()
        orbit_images = set()
        for mapping in group_maps():
            transformed = image(orbit_blocks, mapping)
            orbit_images.add(transformed)
            transformed_low = {
                pair for pair in itertools.combinations(range(1, 12), 2)
                if sum(set(pair) <= set(block) for block in transformed) == 3
            }
            image_alignment_counts.add(len(transformed_low & MATCHING_WITHOUT_FIXED_POINT))
        if len(orbit_images) != orbit["orbit_size"] or len(image_alignment_counts) != 1:
            raise AssertionError("matching-alignment count is not constant on the recorded orbit")
        invariant_images_checked += len(orbit_images)
        quad_multiplicity = [
            sum(set(target) <= set(block) for block in blocks)
            for target in itertools.combinations(range(1, 12), 4)
        ]
        rows.append({
            "orbit_index": index,
            "canonical_sha256": orbit["canonical_sha256"],
            "orbit_size": orbit["orbit_size"],
            "stabilizer_order": orbit["stabilizer_order"],
            "pair_multiplicity_histogram": dict(sorted(collections.Counter(pair_multiplicity.values()).items())),
            "low_pair_graph_degrees": low_degrees,
            "low_pair_graph_triangles": low_triangles,
            "low_pairs_aligned_with_forced_matching": len(low_pairs & MATCHING_WITHOUT_FIXED_POINT),
            "uncovered_nonzero_quadruples": sum(value == 0 for value in quad_multiplicity),
        })
    value: dict[str, object] = {
        "schema_version": 1,
        "catalog_sha256": sha(catalog_path),
        "orbits": rows,
        "observation": "All five links share the forced 20-edge, triangle-free, 4-regular low-pair graph on ten nonexceptional points, but the fifth orbit has two low-pair edges aligned with the forced matching; the earlier orbits realize zero, one, or three.",
        "matching_alignment_branch": {
            "status": "valid_canonical_branch_invariant",
            "definition": "number of multiplicity-3 pairs among the five matching pairs (2,3),(4,5),(6,7),(8,9),(10,11)",
            "possible_values": [0, 1, 2, 3, 4, 5],
            "observed_values": sorted({row["low_pairs_aligned_with_forced_matching"] for row in rows}),
            "orbit_images_exhaustively_checked": invariant_images_checked,
            "proof_basis": "Every element of C2 wr S5 preserves the five matching pairs as a set and preserves pair multiplicity, so the intersection count is orbit-invariant.",
            "recommended_use": "Add this six-way invariant as a structural class and branch-priority feature, not as a completeness assumption; values 4 and 5 remain unobserved rather than excluded.",
        },
        "conditional_low_graph_lemma": {
            "hypotheses": "an exact-degree (10,9,...,9) link in which every pair multiplicity is 3 or 4",
            "conclusion": "the fixed point is isolated in the multiplicity-3 graph and the other ten vertices form a 4-regular graph with 20 edges",
            "proof_basis": "triple coverage gives pair multiplicity at least 3; degree-count sums are 40 at the fixed point and 36 elsewhere, forcing 0 and 4 incident multiplicity-3 pairs respectively under the 3-or-4 hypothesis",
            "scope_limit": "The 3-or-4 hypothesis and triangle-freeness are observed for all five supplied orbits but are not yet proved for every feasible link.",
        },
        "claim_limit": "These are exact structural invariants of the supplied five orbits, not an exhaustive classification or a causal proof of nonextension.",
    }
    if core_path is not None:
        core = json.loads(core_path.read_text())
        counts = collections.Counter(row["kind"] for row in core["semantic_groups"])
        value["fifth_orbit_semantic_core"] = {
            "receipt_sha256": sha(core_path),
            "groups": core["core_groups"],
            "coverage_groups": counts["coverage"],
            "pair_equality_groups": counts["pair_equality"],
            "core_cnf": core["core_cnf"],
        }
    return value


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("catalog", type=Path)
    parser.add_argument("--core", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    value = profile(args.catalog, args.core)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"orbits": len(value["orbits"]), "core_groups": value.get("fifth_orbit_semantic_core", {}).get("groups")}, sort_keys=True))


if __name__ == "__main__":
    main()

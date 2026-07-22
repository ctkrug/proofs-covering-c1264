#!/usr/bin/env python3
"""Split the reported unique C(11,5,3)=20 cover by forced matchings.

The literature statement of ordinary S_11 uniqueness is an external premise.
Everything after that premise (cover validation, automorphisms, matching-orbit
partition, fixed-matching canonicalization, and catalogue comparison) is exact.
"""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
from pathlib import Path

from analyze_link_orbit import PAIRS, group_maps, image
from find_next_link_orbit import LINK_ROOTS, root_orbits, secondary_orbits, tertiary_orbits


ROOT = Path(__file__).resolve().parents[1]
POINTS = tuple(range(1, 12))
LOW_POINTS = tuple(range(2, 12))
PRIMARY_ORBITS = root_orbits()
SECONDARY_ORBITS = {index: secondary_orbits(index) for index in range(len(PRIMARY_ORBITS))}
TERTIARY_ORBITS_00 = tertiary_orbits(0, 0)


def earlier_sets(orbits: list[set[tuple[int, ...]]]) -> list[set[tuple[int, ...]]]:
    accumulated: set[tuple[int, ...]] = set()
    values = []
    for orbit in orbits:
        values.append(set(accumulated))
        accumulated.update(orbit)
    return values


PRIMARY_EARLIER = earlier_sets(PRIMARY_ORBITS)
SECONDARY_EARLIER = {index: earlier_sets(orbits) for index, orbits in SECONDARY_ORBITS.items()}
TERTIARY_EARLIER_00 = earlier_sets(TERTIARY_ORBITS_00)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_blocks(path: Path) -> tuple[tuple[int, ...], ...]:
    blocks = tuple(sorted(tuple(sorted(map(int, row.split()))) for row in path.read_text().splitlines() if row.strip()))
    if len(blocks) != 20 or len(set(blocks)) != 20:
        raise ValueError("expected 20 distinct blocks")
    if any(len(block) != 5 or len(set(block)) != 5 or not set(block) <= set(POINTS) for block in blocks):
        raise ValueError("invalid block")
    if {triple for block in blocks for triple in itertools.combinations(block, 3)} != set(itertools.combinations(POINTS, 3)):
        raise ValueError("not a C(11,5,3) cover")
    return blocks


def normalize_exceptional(blocks: tuple[tuple[int, ...], ...]) -> tuple[tuple[int, ...], ...]:
    degrees = {point: sum(point in block for block in blocks) for point in POINTS}
    exceptional = [point for point, degree in degrees.items() if degree == 10]
    if len(exceptional) != 1 or sorted(degrees.values()) != [9] * 10 + [10]:
        raise ValueError("cover does not have degree vector 10,9^10")
    high = exceptional[0]
    table = {point: point for point in POINTS}
    table[1], table[high] = high, 1
    return tuple(sorted(tuple(sorted(table[point] for point in block)) for block in blocks))


def low_graph(blocks: tuple[tuple[int, ...], ...]) -> dict[int, set[int]]:
    graph = {point: set() for point in LOW_POINTS}
    for a, b in itertools.combinations(LOW_POINTS, 2):
        multiplicity = sum(a in block and b in block for block in blocks)
        if multiplicity == 3:
            graph[a].add(b)
            graph[b].add(a)
        elif multiplicity != 4:
            raise ValueError("unexpected low-point pair multiplicity")
    if any(len(graph[point]) != 4 for point in LOW_POINTS):
        raise ValueError("low-pair graph is not 4-regular")
    return graph


def graph_isomorphisms(
    source: tuple[tuple[int, ...], ...], target: tuple[tuple[int, ...], ...], *, require_blocks: bool
) -> list[tuple[int, ...]]:
    source_graph = low_graph(source)
    target_graph = low_graph(target)
    target_set = set(target)
    order = sorted(LOW_POINTS, key=lambda point: (-sum(len(source_graph[point] & source_graph[q]) for q in source_graph[point]), point))
    mapping = {1: 1}
    used = {1}
    answers: list[tuple[int, ...]] = []

    def visit(index: int) -> None:
        if index == len(order):
            table = tuple(mapping[point] for point in POINTS)
            if not require_blocks or set(image(source, mapping)) == target_set:
                answers.append(table)
            return
        point = order[index]
        for candidate in LOW_POINTS:
            if candidate in used:
                continue
            if all(
                old == 1 or ((old in source_graph[point]) == (new in target_graph[candidate]))
                for old, new in mapping.items()
            ):
                mapping[point] = candidate
                used.add(candidate)
                visit(index + 1)
                used.remove(candidate)
                del mapping[point]

    visit(0)
    return answers


def all_matchings(points: tuple[int, ...]) -> list[tuple[tuple[int, int], ...]]:
    if not points:
        return [()]
    first = points[0]
    values = []
    for index in range(1, len(points)):
        second = points[index]
        rest = points[1:index] + points[index + 1 :]
        for tail in all_matchings(rest):
            values.append(tuple(sorted(((first, second),) + tail)))
    return values


def matching_image(matching: tuple[tuple[int, int], ...], action: tuple[int, ...]) -> tuple[tuple[int, int], ...]:
    return tuple(sorted(tuple(sorted((action[a - 1], action[b - 1]))) for a, b in matching))


def fixed_matching_relabel(
    blocks: tuple[tuple[int, ...], ...], matching: tuple[tuple[int, int], ...]
) -> tuple[tuple[int, ...], ...]:
    mapping = {1: 1}
    for source_pair, target_pair in zip(sorted(matching), PAIRS):
        for source, target in zip(sorted(source_pair), target_pair):
            mapping[source] = target
    return image(blocks, mapping)


def canonical_fixed(blocks: tuple[tuple[int, ...], ...]) -> tuple[tuple[int, ...], ...]:
    return min(image(blocks, mapping) for mapping in group_maps())


def canonical_hash(blocks: tuple[tuple[int, ...], ...]) -> str:
    text = "".join(" ".join(map(str, block)) + "\n" for block in blocks)
    return hashlib.sha256(text.encode("ascii")).hexdigest()


def aligned_route(blocks: tuple[tuple[int, ...], ...]) -> str | None:
    selected = set(blocks)
    primary = PRIMARY_ORBITS
    roots = [index for index, root in enumerate(primary) if LINK_ROOTS[index] in selected and not selected.intersection(PRIMARY_EARLIER[index])]
    if len(roots) != 1:
        return None
    root_index = roots[0]
    secondaries = SECONDARY_ORBITS[root_index]
    seconds = [index for index, orbit in enumerate(secondaries) if min(orbit) in selected and not selected.intersection(SECONDARY_EARLIER[root_index][index])]
    if len(seconds) != 1:
        return None
    secondary_index = seconds[0]
    if root_index == 0 and secondary_index == 0:
        tertiaries = TERTIARY_ORBITS_00
        thirds = [index for index, orbit in enumerate(tertiaries) if min(orbit) in selected and not selected.intersection(TERTIARY_EARLIER_00[index])]
        if len(thirds) != 1:
            return None
        tertiary_index = thirds[0]
        return f"t-{tertiary_index}"
    return f"s-r{root_index}-{secondary_index}"


def reaches_secondary(blocks: tuple[tuple[int, ...], ...], root_index: int, secondary_index: int) -> bool:
    target = f"s-r{root_index}-{secondary_index}"
    return any(aligned_route(image(blocks, mapping)) == target for mapping in group_maps())


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cover", type=Path, required=True)
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    cover_path = args.cover if args.cover.is_absolute() else ROOT / args.cover
    catalog_path = args.catalog if args.catalog.is_absolute() else ROOT / args.catalog
    output_path = args.output if args.output.is_absolute() else ROOT / args.output

    external = normalize_exceptional(read_blocks(cover_path))
    automorphisms = graph_isomorphisms(external, external, require_blocks=True)
    if len(automorphisms) != 240 or len(set(automorphisms)) != 240:
        raise AssertionError("unexpected automorphism group order")

    matchings = set(all_matchings(LOW_POINTS))
    if len(matchings) != 945:
        raise AssertionError("perfect-matching count changed")
    remaining = set(matchings)
    matching_orbits = []
    while remaining:
        representative = min(remaining)
        orbit = {matching_image(representative, action) for action in automorphisms}
        if not orbit <= matchings:
            raise AssertionError("automorphism does not preserve perfect matchings")
        remaining -= orbit
        relabelled = fixed_matching_relabel(external, representative)
        canonical = canonical_fixed(relabelled)
        matching_orbits.append({
            "matching_representative": [list(pair) for pair in representative],
            "matching_orbit_size": len(orbit),
            "cover_matching_stabilizer_order": len(automorphisms) // len(orbit),
            "predicted_fixed_matching_orbit_size": 16 * len(orbit),
            "canonical_sha256": canonical_hash(canonical),
            "canonical_blocks": [list(block) for block in canonical],
            "reaches_hard_prefix": {
                "s-r0-1": reaches_secondary(canonical, 0, 1),
                "s-r1-15": reaches_secondary(canonical, 1, 15),
            },
        })
    matching_orbits.sort(key=lambda row: row["canonical_sha256"])
    if sum(int(row["matching_orbit_size"]) for row in matching_orbits) != 945:
        raise AssertionError("matching orbits do not cover the matching space")

    catalog = json.loads(catalog_path.read_text())
    known = {row["canonical_sha256"]: row for row in catalog["orbits"]}
    predicted = {row["canonical_sha256"]: row for row in matching_orbits}
    if not set(known) <= set(predicted):
        raise AssertionError("campaign catalogue contains a class outside the literature reduction")
    for hash_value, row in predicted.items():
        row["campaign_status"] = "catalogued" if hash_value in known else "missing-from-nine-orbit-catalogue"
        if hash_value in known:
            row["campaign_orbit_size"] = known[hash_value]["orbit_size"]
            if row["campaign_orbit_size"] != row["predicted_fixed_matching_orbit_size"]:
                raise AssertionError("orbit-size cross-check failed")

    campaign_isomorphisms = []
    for index, entry in enumerate(catalog["orbits"], 1):
        source_path = ROOT / entry["source"]["path"]
        candidate = read_blocks(source_path)
        witnesses = graph_isomorphisms(candidate, external, require_blocks=True)
        if not witnesses:
            raise AssertionError("campaign link is not isomorphic to external representative")
        campaign_isomorphisms.append({
            "campaign_orbit_index": index,
            "campaign_canonical_sha256": entry["canonical_sha256"],
            "source_sha256": digest(source_path),
            "external_isomorphism": list(witnesses[0]),
        })

    missing = [row for row in matching_orbits if row["campaign_status"].startswith("missing")]
    result = {
        "schema_version": 1,
        "status": "exact-conditional-reduction",
        "external_premise": {
            "claim": "There is one ordinary S_11-isomorphism class of 20-block C(11,5,3) covers.",
            "status": "reported in peer-reviewed primary literature; proof/census certificate not located",
            "source": "G.H.J. van Rees, Three Constructions of Covers, JCMCC 16 (1994), 19-25, p.22; attribution there is to W.H. Mills, private communication.",
            "url": "https://combinatorialpress.com/article/jcmcc/Volume%2016/vol-16-paper%202.pdf",
            "claim_limit": "The exact 20-class conclusion is conditional on this external uniqueness premise until its proof or an independent exhaustive certificate is obtained.",
        },
        "external_cover": {"path": str(cover_path.relative_to(ROOT)), "sha256": digest(cover_path)},
        "external_cover_validation": {"blocks": 20, "triples_covered": 165, "degree_vector": [10] + [9] * 10},
        "automorphism_group_order": len(automorphisms),
        "perfect_matchings": len(matchings),
        "matching_orbit_count": len(matching_orbits),
        "matching_orbit_sizes": sorted(int(row["matching_orbit_size"]) for row in matching_orbits),
        "campaign_catalogue": {
            "path": str(catalog_path.relative_to(ROOT)),
            "sha256": digest(catalog_path),
            "known_classes": len(known),
            "predicted_missing_classes": len(missing),
            "known_subset_verified": True,
        },
        "campaign_isomorphisms": campaign_isomorphisms,
        "matching_orbits": matching_orbits,
        "hard_tail_hypothesis": {
            "statement": "The two 60-second survivors remain open because the nine-orbit blocker omits ordinary-cover/fixed-matching embeddings routed through those prefixes.",
            "falsifier": "The exact matching split assigns no missing class to one or both hard prefixes.",
            "observed_missing_in_s_r0_1": sum(row["reaches_hard_prefix"]["s-r0-1"] for row in missing),
            "observed_missing_in_s_r1_15": sum(row["reaches_hard_prefix"]["s-r1-15"] for row in missing),
        },
        "claim_limit": "Exact after the stated ordinary-uniqueness premise; not an unconditional exhaustive classification theorem.",
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"status": result["status"], "matching_orbits": len(matching_orbits), "missing": len(missing), "hard_tail_hypothesis": result["hard_tail_hypothesis"]}, sort_keys=True))


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Build, but do not solve, the 20 conditional fixed-link residual CNFs."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from run_link_residual_pilot import build


ROOT = Path(__file__).resolve().parents[1]


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def record(path: Path) -> dict[str, object]:
    return {"path": str(path.relative_to(ROOT)), "bytes": path.stat().st_size, "sha256": sha(path)}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--classification",
        type=Path,
        default=ROOT / "artifacts/prior-art/c1153-literature-matching-split.json",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "artifacts/prior-art/c1153-direct-20",
    )
    args = parser.parse_args()
    classification_path = args.classification if args.classification.is_absolute() else ROOT / args.classification
    output = args.output if args.output.is_absolute() else ROOT / args.output
    if output.exists():
        raise FileExistsError(f"refusing to overwrite {output}")
    output.mkdir(parents=True)

    source = json.loads(classification_path.read_text(encoding="utf-8"))
    rows: list[dict[str, object]] = []
    for index, item in enumerate(source["matching_orbits"], 1):
        unit = output / f"class-{index:02d}"
        unit.mkdir()
        link_path = unit / "link.txt"
        link_path.write_text(
            "".join(" ".join(map(str, block)) + "\n" for block in item["canonical_blocks"]),
            encoding="utf-8",
        )
        cnf, _links, residual, ranges, coverage_count = build(link_path)
        cnf_path = unit / "instance.cnf"
        cnf.to_file(str(cnf_path))
        result = {
            "schema_version": 1,
            "status": "NOT_SOLVED",
            "class_index": index,
            "canonical_sha256": item["canonical_sha256"],
            "campaign_status": item["campaign_status"],
            "link": record(link_path),
            "primary_variables": len(residual),
            "variables": cnf.nv,
            "clauses": len(cnf.clauses),
            "residual_coverage_constraints": coverage_count,
            "residual_pair_equalities": 55,
            "auxiliary_ranges": ranges,
            "cnf": record(cnf_path),
            "claim_limit": (
                "This is an unsolved exact residual-extension instance for one matching class. "
                "The 20-way exhaustion claim remains conditional on a proof of ordinary-cover uniqueness."
            ),
        }
        result_path = unit / "result.json"
        result_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        rows.append({**result, "result": record(result_path)})

    manifest = {
        "schema_version": 1,
        "status": "built_not_solved",
        "classification": record(classification_path),
        "case_count": len(rows),
        "cases": rows,
        "total_cnf_bytes": sum(int(row["cnf"]["bytes"]) for row in rows),
        "claim_limit": (
            "All 20 CNFs are exact for their stated fixed-link representatives. They are exhaustive for "
            "hypothetical 40-covers only if the cited ordinary C(11,5,3)=20 uniqueness premise is proved."
        ),
    }
    manifest_path = output / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"cases": len(rows), "bytes": manifest["total_cnf_bytes"], "manifest_sha256": sha(manifest_path)}))


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Independently audit bounded cube-sample rows against a frozen frontier."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


ALLOWED_STATUSES = {"SAT", "CLOSED_PROVISIONAL", "UNKNOWN", "ERROR"}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def atomic_json(path: Path, value: dict[str, object]) -> None:
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def audit(frontier_path: Path, result_paths: list[Path]) -> dict[str, object]:
    frontier = json.loads(frontier_path.read_text(encoding="utf-8"))
    cubes = {
        int(cube["cube_id"]): tuple(int(literal) for literal in cube["literals"])
        for cube in frontier["cubes"]
    }
    if len(cubes) != len(frontier["cubes"]):
        raise ValueError("frontier contains duplicate cube IDs")

    rows: list[dict[str, object]] = []
    files: list[dict[str, object]] = []
    seen: set[int] = set()
    for path in result_paths:
        file_rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        if not file_rows:
            raise ValueError(f"empty results file: {path}")
        files.append({"path": str(path), "sha256": sha(path), "rows": len(file_rows)})
        for row in file_rows:
            cube_id = int(row["cube_id"])
            literals = tuple(int(literal) for literal in row["literals"])
            status = str(row["status"])
            if cube_id in seen:
                raise ValueError(f"duplicate sampled cube ID: {cube_id}")
            if cube_id not in cubes or literals != cubes[cube_id]:
                raise ValueError(f"sample row does not match frontier cube: {cube_id}")
            if status not in ALLOWED_STATUSES:
                raise ValueError(f"unrecognized cube status: {status}")
            if float(row["elapsed_seconds"]) < 0:
                raise ValueError("negative elapsed time")
            if status == "SAT" and not row.get("positive_primary_literals"):
                raise ValueError("SAT row lacks a primary-variable model")
            seen.add(cube_id)
            rows.append(row)

    counts = {status: sum(row["status"] == status for row in rows) for status in sorted(ALLOWED_STATUSES)}
    determinate = counts["SAT"] + counts["CLOSED_PROVISIONAL"]
    return {
        "schema_version": 1,
        "status": "valid" if counts["ERROR"] == 0 else "invalid",
        "root_case": frontier["root_case"],
        "frontier": {"path": str(frontier_path), "sha256": sha(frontier_path)},
        "sample_files": files,
        "sampled_cube_ids": sorted(seen),
        "sampled_cubes": len(rows),
        "status_counts": counts,
        "determinate_fraction": determinate / len(rows),
        "closed_provisional_fraction": counts["CLOSED_PROVISIONAL"] / len(rows),
        "elapsed_seconds": sum(float(row["elapsed_seconds"]) for row in rows),
        "claim_limit": (
            "CLOSED_PROVISIONAL records solver verdicts only; they do not become proved closed "
            "leaves without independently replayed proof artifacts. UNKNOWN is inconclusive."
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("frontier", type=Path)
    parser.add_argument("results", nargs="+", type=Path)
    parser.add_argument("--receipt", type=Path)
    args = parser.parse_args()
    result = audit(args.frontier, args.results)
    if args.receipt:
        atomic_json(args.receipt, result)
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()

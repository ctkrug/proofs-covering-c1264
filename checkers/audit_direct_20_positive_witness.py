#!/usr/bin/env python3
"""Independent direct checker for a candidate 40-block C(12,6,4) cover."""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("witness", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    blocks = [tuple(sorted(int(value) for value in raw.split())) for raw in args.witness.read_text().splitlines() if raw.strip()]
    valid_blocks = len(blocks) == 40 and len(set(blocks)) == 40 and all(
        len(block) == 6 and len(set(block)) == 6 and block[0] >= 1 and block[-1] <= 12 for block in blocks
    )
    targets = list(itertools.combinations(range(1, 13), 4))
    covered = sum(any(set(target) <= set(block) for block in blocks) for target in targets) if valid_blocks else 0
    payload = {
        "schema_version": 1,
        "status": "VALID_40_COVER" if valid_blocks and covered == 495 else "INVALID",
        "blocks": len(blocks),
        "distinct_blocks": len(set(blocks)),
        "covered_quadruples": covered,
        "total_quadruples": 495,
        "witness_sha256": hashlib.sha256(args.witness.read_bytes()).hexdigest(),
    }
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(payload, sort_keys=True))
    if payload["status"] != "VALID_40_COVER":
        raise SystemExit(1)


if __name__ == "__main__":
    main()

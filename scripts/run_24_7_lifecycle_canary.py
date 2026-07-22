#!/usr/bin/env python3
"""Two-segment, dependency-free canary for the durable Proof Factory lifecycle."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from checkers.verify_cover import verify  # noqa: E402


ARTIFACT_ROOT = ROOT / "artifacts" / "24-7-lifecycle-canary"
CHECKPOINT = ARTIFACT_ROOT / "checkpoint.json"
PROGRESS = ARTIFACT_ROOT / "progress.json"
WITNESS = ROOT / "sources" / "ljcr-c1264-41.txt"


def write_atomic(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def main() -> None:
    prior = json.loads(CHECKPOINT.read_text(encoding="utf-8")) if CHECKPOINT.is_file() else {"segments": 0}
    segment = int(prior.get("segments", 0)) + 1
    result = verify(WITNESS, v=12, k=6, t=4, expected_blocks=41)
    if result.get("status") != "valid" or result.get("covered_t_sets") != 495:
        raise RuntimeError("direct C(12,6,4) witness check did not produce the declared control signal")

    checkpoint = {
        "schema_version": 1,
        "segments": segment,
        "last_result": result,
    }
    write_atomic(CHECKPOINT, checkpoint)
    artifact_bytes = CHECKPOINT.stat().st_size
    progress = {
        "completed_units": min(segment, 2),
        "total_units": 2,
        "complete": segment >= 2,
        "correctness_checks_passed": True,
        "decision_value_active": segment <= 2,
        "artifact_bytes": artifact_bytes,
    }
    write_atomic(PROGRESS, progress)
    print(json.dumps({"checkpoint": checkpoint, "progress": progress}, sort_keys=True))


if __name__ == "__main__":
    main()

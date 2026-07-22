#!/usr/bin/env python3
"""Two-segment, dependency-free canary for the durable Proof Factory lifecycle."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SAFE_RUN_ID = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")


def write_atomic(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--checker", type=Path, required=True)
    parser.add_argument("--witness", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args()
    if not SAFE_RUN_ID.fullmatch(args.run_id):
        raise ValueError("run-id must contain only lowercase letters, digits, and hyphens")
    checker = (ROOT / args.checker).resolve()
    witness = (ROOT / args.witness).resolve()
    checker.relative_to(ROOT)
    witness.relative_to(ROOT)
    module_spec = importlib.util.spec_from_file_location("c1264_direct_checker", checker)
    if module_spec is None or module_spec.loader is None:
        raise RuntimeError("unable to load direct checker")
    checker_module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(checker_module)

    artifact_root = ROOT / "artifacts" / "lifecycle-canary" / args.run_id
    checkpoint_path = artifact_root / "checkpoint.json"
    progress_path = artifact_root / "progress.json"
    prior = json.loads(checkpoint_path.read_text(encoding="utf-8")) if checkpoint_path.is_file() else {"segments": 0}
    segment = int(prior.get("segments", 0)) + 1
    result = checker_module.verify(witness, v=12, k=6, t=4, expected_blocks=41)
    if result.get("status") != "valid" or result.get("covered_t_sets") != 495:
        raise RuntimeError("direct C(12,6,4) witness check did not produce the declared control signal")

    checkpoint = {
        "schema_version": 1,
        "segments": segment,
        "last_result": result,
    }
    write_atomic(checkpoint_path, checkpoint)
    artifact_bytes = checkpoint_path.stat().st_size
    progress = {
        "completed_units": min(segment, 2),
        "total_units": 2,
        "complete": segment >= 2,
        "correctness_checks_passed": True,
        "decision_value_active": segment <= 2,
        "artifact_bytes": artifact_bytes,
    }
    write_atomic(progress_path, progress)
    print(json.dumps({"checkpoint": checkpoint, "progress": progress}, sort_keys=True))


if __name__ == "__main__":
    main()

import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "artifacts/classification/ordinary-c1153-v1/hard-tail-fifth-split/terminal-aggregate-audit-full-replay.json"


def test_terminal_aggregate_rebuilds_and_preserves_ledger_separation() -> None:
    subprocess.run(
        [str(ROOT / ".venv/bin/python"), str(ROOT / "checkers/audit_ordinary_c1153_fifth_terminal_state.py")],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    report = json.loads(REPORT.read_text())
    assert report["status"] == "VALID"
    assert report["counts"] == {
        "certified_unsat_distinct": 32_611,
        "complete_fourth_parents": 0,
        "fifth_branches_total": 43_319,
        "measured_distinct": 32_693,
        "never_measured": 10_626,
        "open_distinct": 10_708,
        "provisional_unsat_backlog": 0,
        "sat": 0,
        "solver_or_replay_unsat_distinct": 32_611,
        "timeouts": 82,
    }
    assert report["suffix"]["selected"] == 32_597
    assert report["hard_tail"]["audited_sixth_snapshot_timeouts"] == 48
    assert report["hard_tail"]["later_timeouts_requiring_fresh_manifest"] == 34

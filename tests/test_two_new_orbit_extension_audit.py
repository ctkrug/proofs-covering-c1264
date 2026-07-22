from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]


def test_two_new_orbit_extension_audit_is_reproducible() -> None:
    run = subprocess.run(
        [sys.executable, str(ROOT / "scripts/record_two_new_orbit_extension_audit.py")],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert run.returncode == 0, run.stderr
    assert '"status": "verified_two_fixed_link_nonextensions"' in run.stdout

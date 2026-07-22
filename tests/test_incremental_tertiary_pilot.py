from __future__ import annotations

import importlib.util
import itertools
import json
import sys
import tempfile
import unittest
from pathlib import Path

from pysat.formula import CNF


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


runner = load("run_incremental_tertiary_pilot", ROOT / "scripts" / "run_incremental_tertiary_pilot.py")
auditor = load("audit_incremental_tertiary_pilot", ROOT / "checkers" / "audit_incremental_tertiary_pilot.py")
finder = load("find_next_link_orbit_for_incremental_test", ROOT / "scripts" / "find_next_link_orbit.py")
BLOCKER = ROOT / "artifacts" / "pilot" / "link-orbit-catalog-3-blocking.cnf"


class IncrementalTertiaryPilotTests(unittest.TestCase):
    def fixture(self) -> Path:
        return (
            ROOT / "artifacts" / "pilot"
            / "link-orbit-incremental-tertiary-pilot-1000conflicts" / "result.json"
        )

    def assert_mutation_rejected(self, mutate) -> None:
        fixture = self.fixture()
        if not fixture.exists():
            self.skipTest("pilot fixture is generated after the preflight tests")
        payload = json.loads(fixture.read_text())
        mutate(payload)
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "mutated.json"
            path.write_text(json.dumps(payload))
            with self.assertRaises(ValueError):
                auditor.audit(path)

    def test_assumptions_exactly_reconstruct_selected_hard_tail_units(self) -> None:
        parent, blocks, _, _, _ = finder.build(BLOCKER, 0, 0)
        plan = runner.assumption_plan(blocks, [0, 3, 9])
        self.assertEqual([len(row["assumptions"]) for row in plan], [1, 13, 35])
        for row in plan:
            index = row["tertiary_index"]
            reference = CNF(from_file=str(
                ROOT / "artifacts" / "pilot"
                / f"link-orbit-root0-secondary-0-tertiary-{index}-10s" / "instance.cnf"
            ))
            self.assertEqual(reference.clauses, parent.clauses + [[x] for x in row["assumptions"]])

    def test_independent_partition_matches_producer(self) -> None:
        second, independent = auditor.independent_partition()
        self.assertEqual(second, min(finder.secondary_orbits(0)[0]))
        self.assertEqual(independent, finder.tertiary_orbits(0, 0))
        self.assertEqual(len(set().union(*independent)), len(list(itertools.combinations(range(1, 12), 5))) - 2)

    def test_parse_indices_rejects_duplicate_and_unsorted(self) -> None:
        with self.assertRaises(ValueError):
            runner.parse_indices("0,0", 122)
        with self.assertRaises(ValueError):
            runner.parse_indices("2,1", 122)

    def test_auditor_rejects_mutated_assumption(self) -> None:
        self.assert_mutation_rejected(lambda value: value["leaves"][0]["assumptions"].__setitem__(0, -value["leaves"][0]["assumptions"][0]))

    def test_auditor_rejects_mutated_runner_hash(self) -> None:
        self.assert_mutation_rejected(lambda value: value["environment"].__setitem__("script_sha256", "0" * 64))

    def test_auditor_rejects_mutated_aggregate_count(self) -> None:
        self.assert_mutation_rejected(lambda value: value["cold"]["verdict_counts"].__setitem__("UNKNOWN", 9))

    def test_auditor_rejects_nonopen_reference(self) -> None:
        self.assert_mutation_rejected(lambda value: value["leaves"][0]["reference"].__setitem__("prior_status", "UNSAT_PROVISIONAL"))

    def test_auditor_rejects_witness_on_unknown_row(self) -> None:
        self.assert_mutation_rejected(lambda value: value["incremental"]["rows"][0].__setitem__("witness", {}))

    def test_auditor_accepts_both_frozen_pilots(self) -> None:
        paths = [
            ROOT / "artifacts" / "pilot" / "link-orbit-incremental-tertiary-pilot-1s" / "result.json",
            self.fixture(),
        ]
        if not all(path.exists() for path in paths):
            self.skipTest("pilot fixtures are generated after the preflight tests")
        for path in paths:
            self.assertEqual(auditor.audit(path)["status"], "valid-exploratory-best-effort-pilot")


if __name__ == "__main__":
    unittest.main()

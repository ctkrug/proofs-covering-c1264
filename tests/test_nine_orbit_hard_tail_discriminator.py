import copy
import json
from pathlib import Path

import pytest

from scripts import build_nine_orbit_hard_tail_discriminator as target


ROOT = Path(__file__).resolve().parents[1]


def test_frozen_selection_and_current_bindings() -> None:
    value = json.loads((ROOT / target.OUTPUT).read_text())
    portfolio = json.loads((ROOT / target.SNAPSHOT).read_text())
    index = json.loads((ROOT / target.INDEX).read_text())
    target.validate(value, portfolio, index, target.SNAPSHOT)
    assert [row["id"] for row in value["leaves"]] == ["s-r0-1", "s-r1-15", "t-10"]
    assert value["seconds_per_run"] == 60
    assert value["blocking_cnf"].endswith("link-orbit-catalog-9-blocking.cnf")


def test_rejects_durable_overlap() -> None:
    value = json.loads((ROOT / target.OUTPUT).read_text())
    portfolio = json.loads((ROOT / target.SNAPSHOT).read_text())
    index = json.loads((ROOT / target.INDEX).read_text())
    broken = copy.deepcopy(value)
    broken["leaves"][0]["id"] = index["closed_node_ids"][0]
    with pytest.raises(ValueError, match="order changed"):
        target.validate(broken, portfolio, index, target.SNAPSHOT)

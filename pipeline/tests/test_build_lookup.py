"""Tests for the display-group rollup used to build the lookup shards."""

from pathlib import Path

import pandas as pd

from hwid_pipeline.build_lookup import display_map

MAPPINGS = Path("mappings")


def _display_map() -> dict[int, int]:
    causes = pd.read_csv(MAPPINGS / "ghe_causes.csv")
    roots = set(pd.read_csv(MAPPINGS / "display_groups.csv")["root_ghe_id"])
    return display_map(causes, roots)


def test_rollup_to_display_groups() -> None:
    dm = _display_map()
    assert dm[680] == 610  # lung cancer -> Cancers
    assert dm[700] == 610  # breast cancer -> Cancers
    assert dm[1130] == 1130  # ischaemic heart disease is its own group
    assert dm[1120] == 1100  # hypertensive heart disease -> other heart and circulatory
    assert dm[950] == 950  # dementia is its own group
    assert dm[1610] == 1610  # self-harm is its own group
    assert dm[1550] == 1520  # falls -> other unintentional injury


def test_every_cause_maps_to_a_root() -> None:
    causes = pd.read_csv(MAPPINGS / "ghe_causes.csv")
    roots = set(pd.read_csv(MAPPINGS / "display_groups.csv")["root_ghe_id"])
    dm = display_map(causes, roots)
    assert all(v in roots for v in dm.values())

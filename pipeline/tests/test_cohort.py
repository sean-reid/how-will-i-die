"""The cohort integration yields lifetime cause shares that sum to one."""

import collections

import numpy as np
import pandas as pd

from hwid_pipeline.project.cohort import lifetime_causes
from hwid_pipeline.project.composition import fit_composition
from hwid_pipeline.project.lee_carter import fit_lee_carter

AGES = [0, 1, 5, 85]
YEARS = list(range(2000, 2020))


def _fits():
    a = np.array([-4.0, -7.0, -6.0, -1.0])
    b = np.array([0.25, 0.25, 0.25, 0.25])
    ktrue = np.linspace(0.5, -0.5, len(YEARS))
    mrows = []
    for i, yr in enumerate(YEARS):
        mx = np.exp(a + b * ktrue[i])
        for j, age in enumerate(AGES):
            mrows.append((yr, age, float(mx[j])))
    lc = fit_lee_carter(pd.DataFrame(mrows, columns=["year", "age_start", "mx"]), YEARS)

    drows = []
    for yr in YEARS:
        for band, (c1, c2) in [(0, (30, 70)), (5, (50, 50)), (85, (60, 40))]:
            drows.append((yr, band, 100, c1))
            drows.append((yr, band, 200, c2))
    comp = fit_composition(
        pd.DataFrame(drows, columns=["year", "age_start", "ghe_id", "deaths"]), YEARS
    )
    return lc, comp


def test_lifetime_shares_sum_to_one_per_start_band() -> None:
    lc, comp = _fits()
    rows = lifetime_causes(lc, comp)
    totals = collections.defaultdict(float)
    for start, _end, _gid, prob, _lo, _hi in rows:
        totals[start] += prob
    assert totals  # produced something
    for value in totals.values():
        assert abs(value - 1.0) < 1e-9
    assert 1 not in totals  # the 1-4 split is not a start band


def test_probabilities_within_unit_interval() -> None:
    lc, comp = _fits()
    for _start, _end, _gid, prob, lo, hi in lifetime_causes(lc, comp):
        assert 0.0 <= prob <= 1.0
        assert 0.0 <= lo <= hi <= 1.0

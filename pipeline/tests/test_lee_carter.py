"""Lee-Carter recovers a known rank-one trend and reconstructs its rates."""

import numpy as np
import pandas as pd

from hwid_pipeline.project.lee_carter import fit_lee_carter

AGES = [0, 1, 5, 10, 15]
YEARS = list(range(2000, 2020))
A = np.array([-3.0, -6.0, -7.0, -6.5, -6.0])
B = np.array([0.35, 0.15, 0.10, 0.15, 0.25])  # sums to 1
KTRUE = np.linspace(1.0, -1.0, len(YEARS))  # mean 0, declining


def _synthetic() -> pd.DataFrame:
    rows = []
    for i, yr in enumerate(YEARS):
        mx = np.exp(A + B * KTRUE[i])
        for j, age in enumerate(AGES):
            rows.append((yr, age, float(mx[j])))
    return pd.DataFrame(rows, columns=["year", "age_start", "mx"])


def test_drift_is_negative_when_mortality_falls() -> None:
    lc = fit_lee_carter(_synthetic(), YEARS)
    assert lc.drift < 0


def test_reconstructs_fitted_rates() -> None:
    lc = fit_lee_carter(_synthetic(), YEARS)
    got = lc.mx_vector(2010)
    expected = np.exp(A + B * KTRUE[YEARS.index(2010)])
    assert np.allclose(got, expected, rtol=1e-6)


def test_forecast_stays_positive() -> None:
    lc = fit_lee_carter(_synthetic(), YEARS)
    assert (lc.mx_vector(2040) > 0).all()

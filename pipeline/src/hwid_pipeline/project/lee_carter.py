"""Lee-Carter model of the all-cause mortality level.

Fits ln m(x,t) = a(x) + b(x) k(t) per country and sex, forecasts the time
index k with a damped random-walk drift estimated from the pre-COVID window,
and floors projected rates so they cannot overshoot toward zero.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

FIT_YEARS = list(range(2000, 2020))  # 2000-2019 inclusive; excludes the COVID years
JUMPOFF = 2019
PHI = 0.98  # drift damping per forecast year
# Cap the drift standard error so a country with a noisy time index cannot blow
# the interval up over a long horizon. Set above the stable large countries
# (whose drift_se tops out near 0.37), so it only bites genuine outliers.
DRIFT_SE_CAP = 0.5


@dataclass
class LeeCarter:
    ages: np.ndarray  # band start age, sorted (matches the life-table bands)
    a: np.ndarray  # average log-rate by age
    b: np.ndarray  # age sensitivity to the time index (sums to 1)
    k: dict[int, float]  # fitted time index by year
    drift: float
    drift_se: float
    jump: int  # jump-off year
    hist_min_mx: np.ndarray  # smallest observed rate per age, used as a floor
    phi: float = PHI

    def k_at(self, year: int, drift: float | None = None) -> float:
        if year in self.k:
            return self.k[year]
        d = self.drift if drift is None else drift
        h = year - self.jump
        damp = h if self.phi == 1 else (1 - self.phi**h) / (1 - self.phi)
        return self.k[self.jump] + d * damp

    def mx_vector(self, year: int, drift: float | None = None) -> np.ndarray:
        mx = np.exp(self.a + self.b * self.k_at(year, drift))
        return np.maximum(mx, 0.5 * self.hist_min_mx)


def fit_lee_carter(df: pd.DataFrame, fit_years: list[int]) -> LeeCarter:
    """df has columns year, age_start, mx for a single country and sex."""
    piv = (
        df[df["year"].isin(fit_years)]
        .pivot(index="age_start", columns="year", values="mx")
        .sort_index()
    )
    ages = piv.index.to_numpy()
    years = list(piv.columns)
    # Floor against the occasional nonpositive life-table cell in a few smaller
    # countries so the log and SVD stay finite. A no-op for well-behaved rates.
    rates = np.maximum(piv.to_numpy(), 1e-9)
    logm = np.log(rates)

    a = logm.mean(axis=1)
    z = logm - a[:, None]
    u, s, vt = np.linalg.svd(z, full_matrices=False)
    b = u[:, 0]
    k = s[0] * vt[0, :]

    # Identify: b sums to 1, k centered to mean zero (folded back into a).
    scale = b.sum()
    b = b / scale
    k = k * scale
    kbar = k.mean()
    a = a + b * kbar
    k = k - kbar

    kd = {int(yr): float(k[i]) for i, yr in enumerate(years)}
    jump = max(fit_years)
    first = min(fit_years)
    drift = (kd[jump] - kd[first]) / (jump - first)
    diffs = np.diff([kd[y] for y in sorted(kd)])
    drift_se = min(float(diffs.std(ddof=1) / np.sqrt(len(diffs))), DRIFT_SE_CAP)

    return LeeCarter(
        ages=ages,
        a=a,
        b=b,
        k=kd,
        drift=drift,
        drift_se=drift_se,
        jump=jump,
        hist_min_mx=rates.min(axis=1),
    )

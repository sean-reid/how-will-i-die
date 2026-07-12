"""Coherent forecast of the cause composition at each age.

The share of deaths by cause within an age band is a composition (sums to one).
We forecast it in centered-log-ratio space so the forecast stays positive and
sums to one, shrink noisy trends for rare causes, and inverse-transform back to
shares.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .lee_carter import JUMPOFF

ZERO_DELTA = 1e-6
SHRINK_TAU = 0.01
# Damping for the composition trend. Applied as a cumulative damped sum so the
# trend saturates within roughly a decade: over a lifetime horizon we do not
# know the future cause mix, so the forecast stays near the recent observed
# composition rather than extrapolating a 20-year slope for 80 years.
COMP_PHI = 0.90


@dataclass
class BandFit:
    ids: np.ndarray  # GHE cause ids present in this band
    clr_jump: np.ndarray  # centered log-ratio at the jump-off year
    trend: np.ndarray  # shrunken slope per cause (already weighted)
    trend_se: np.ndarray  # sampling std of the shrunken slope, for uncertainty draws


class Composition:
    """Cause shares by (age band, year), forecast per band."""

    def __init__(self, bands: dict[int, BandFit]):
        self.bands = bands

    def frac_vector(self, band: int, year: int, index: dict[int, int]) -> np.ndarray:
        fit = self.bands[band]
        h = year - JUMPOFF
        damp = 0.0 if h <= 0 else (1 - COMP_PHI**h) / (1 - COMP_PHI)
        clr = fit.clr_jump + fit.trend * damp
        e = np.exp(clr - clr.max())
        f = e / e.sum()
        out = np.zeros(len(index))
        for j, gid in enumerate(fit.ids):
            out[index[int(gid)]] += f[j]
        return out

    def frac_matrix(self, band: int, year: int, index: dict[int, int], z: np.ndarray) -> np.ndarray:
        """Shares for many draws at once. z is (n_draws, n_causes) standard normals.

        Each draw perturbs the cause-trend slopes by their sampling error, so the
        forecast composition varies across draws. The perturbation is scaled by
        the same horizon damping as the point forecast, so longer projections
        (younger cohorts) get proportionally wider spread.
        """
        fit = self.bands[band]
        h = year - JUMPOFF
        damp = 0.0 if h <= 0 else (1 - COMP_PHI**h) / (1 - COMP_PHI)
        trend = fit.trend[None, :] + fit.trend_se[None, :] * z
        clr = fit.clr_jump[None, :] + trend * damp
        e = np.exp(clr - clr.max(axis=1, keepdims=True))
        f = e / e.sum(axis=1, keepdims=True)
        out = np.zeros((z.shape[0], len(index)))
        for j, gid in enumerate(fit.ids):
            out[:, index[int(gid)]] += f[:, j]
        return out


def fit_composition(df: pd.DataFrame, fit_years: list[int]) -> Composition:
    """df has columns year, age_start, ghe_id, deaths for a single country and sex."""
    bands: dict[int, BandFit] = {}
    yrs = np.array(fit_years, dtype=float)
    centered_year = yrs - yrs.mean()
    denom = (centered_year**2).sum()
    jump_row = fit_years.index(JUMPOFF)

    for band, g in df.groupby("age_start"):
        piv = (
            g[g["year"].isin(fit_years)]
            .pivot_table(
                index="year", columns="ghe_id", values="deaths", aggfunc="sum", fill_value=0.0
            )
            .reindex(fit_years)
            .fillna(0.0)
        )
        ids = piv.columns.to_numpy()
        counts = piv.to_numpy(dtype=float)
        total = counts.sum(axis=1, keepdims=True)
        total[total == 0] = 1.0
        frac = counts / total

        # multiplicative zero replacement, then renormalize
        frac = np.where(frac <= 0, ZERO_DELTA, frac)
        frac = frac / frac.sum(axis=1, keepdims=True)

        logf = np.log(frac)
        clr = logf - logf.mean(axis=1, keepdims=True)
        slope = (clr * centered_year[:, None]).sum(axis=0) / denom

        # Sampling std of each slope, from the regression residuals.
        fitted = clr.mean(axis=0)[None, :] + slope[None, :] * centered_year[:, None]
        resid = clr - fitted
        dof = max(len(fit_years) - 2, 1)
        sigma = np.sqrt((resid**2).sum(axis=0) / dof)
        slope_se = sigma / np.sqrt(denom)

        mean_share = frac.mean(axis=0)
        weight = mean_share / (mean_share + SHRINK_TAU)

        bands[int(band)] = BandFit(
            ids=ids,
            clr_jump=clr[jump_row],
            trend=weight * slope,
            trend_se=weight * slope_se,
        )

    return Composition(bands)

"""Cohort-diagonal competing-risks integration.

For a cohort alive at a given age today, march forward along the age diagonal
(age x+k is experienced in calendar year base+k), applying projected all-cause
survival and the projected cause composition, and accumulate each cause's
lifetime cumulative incidence. Because the open terminal band is fully absorbing
and each band's cause shares sum to one, the lifetime cause shares sum to one.
"""

from __future__ import annotations

import numpy as np

from .composition import Composition
from .lee_carter import LeeCarter

NOW_YEAR = 2025
N_DRAWS = 200
SEED = 20260711
HORIZON_REF = 65.0

# The interval is the data-driven draw spread, clamped to a plausible relative
# half-width that grows with the projection horizon. The cap stops a noisy
# country from producing a wild band; for modeled GHE data a floor makes those
# countries visibly less certain than the registered MDB ones.
#   cap   = CAP_BASE + CAP_SLOPE * horizon_fraction
#   ghe: floor = GHE_FLOOR_BASE + GHE_FLOOR_SLOPE * horizon_fraction, cap *= GHE_CAP_MULT
CAP_BASE = 0.25
CAP_SLOPE = 0.45
GHE_FLOOR_BASE = 0.30
GHE_FLOOR_SLOPE = 0.35
GHE_CAP_MULT = 1.4
# Absolute ceiling on the half-width so no band exceeds a readable span, even for
# the youngest, longest-horizon modeled cohorts (a "5 to 90%" range is useless).
ABS_HALF_CAP = 0.20


def _containing_band(lt_age: int, band_starts: list[int]) -> int:
    # Assign each fine life-table band the cause shares of the coarser cause band
    # it nests inside: the largest cause-band start not exceeding this age. When
    # the cause grid equals the life-table grid (MDB countries) this reproduces
    # the old mapping exactly, including infants (ages 0 and 1 both map to 0).
    chosen = band_starts[0]
    for start in band_starts:
        if start <= lt_age:
            chosen = start
        else:
            break
    return chosen


def _damp(h: int, phi: float) -> float:
    return h if phi == 1 else (1 - phi**h) / (1 - phi)


def lifetime_causes(lc: LeeCarter, comp: Composition, source: str = "mdb") -> list[tuple]:
    """Return (start_age, end_age, ghe_id, prob, prob_lo, prob_hi) rows."""
    ages = [int(x) for x in lc.ages]
    n_bands = len(ages)
    widths = [ages[i + 1] - ages[i] for i in range(n_bands - 1)] + [np.inf]
    band_starts = sorted(comp.bands)  # cause-band starts (18 for MDB, 7 for GHE)

    union = sorted({int(g) for f in comp.bands.values() for g in f.ids})
    index = {gid: i for i, gid in enumerate(union)}

    rng = np.random.default_rng(SEED)
    draws = rng.normal(lc.drift, lc.drift_se, N_DRAWS)
    # Per-band composition perturbations: each draw also gets its own sampled
    # cause-trend trajectory, so the bands reflect cause-mix uncertainty too.
    z_by_band = {
        b: rng.standard_normal((N_DRAWS, len(fit.ids))) for b, fit in sorted(comp.bands.items())
    }

    start_ages = [a for a in ages if a != 1]  # cause-band starts; skip the 1-4 split
    rows: list[tuple] = []

    for start in start_ages:
        i0 = ages.index(start)
        surv_pt = 1.0
        surv_dr = np.ones(N_DRAWS)
        pi_pt = np.zeros(len(union))
        pi_dr = np.zeros((N_DRAWS, len(union)))

        for b in range(i0, n_bands):
            diag_year = NOW_YEAR + (ages[b] - start)
            h = diag_year - lc.jump
            damp = _damp(h, lc.phi)
            k_pt = lc.k[lc.jump] + lc.drift * damp
            # Central path is damped, but the drift-estimation uncertainty
            # accumulates with the raw horizon like a random walk, so a 20-year
            # projection is honestly wider than a 5-year one.
            k_dr = k_pt + (draws - lc.drift) * h
            floor = 0.5 * lc.hist_min_mx[b]
            mx_pt = max(float(np.exp(lc.a[b] + lc.b[b] * k_pt)), floor)
            mx_dr = np.maximum(np.exp(lc.a[b] + lc.b[b] * k_dr), floor)

            if b == n_bands - 1:  # open terminal band absorbs everyone left
                q_pt = 1.0
                q_dr = np.ones(N_DRAWS)
            else:
                w = widths[b]
                q_pt = 1.0 - np.exp(-w * mx_pt)
                q_dr = 1.0 - np.exp(-w * mx_dr)

            dd_pt = surv_pt * q_pt
            dd_dr = surv_dr * q_dr
            cb = _containing_band(ages[b], band_starts)
            f = comp.frac_vector(cb, diag_year, index)
            fm = comp.frac_matrix(cb, diag_year, index, z_by_band[cb])
            pi_pt += dd_pt * f
            pi_dr += dd_dr[:, None] * fm
            surv_pt *= 1.0 - q_pt
            surv_dr *= 1.0 - q_dr

        if abs(pi_pt.sum() - 1.0) > 1e-9:
            raise ValueError(f"lifetime shares do not sum to 1 (start {start}): {pi_pt.sum()}")

        # Data-driven band from the draws, then a horizon- and source-aware
        # relative-half-width clamp (see the constants above): cap tames a noisy
        # country, and the GHE floor makes modeled data visibly less certain.
        lo = np.percentile(pi_dr, 5, axis=0)
        hi = np.percentile(pi_dr, 95, axis=0)
        hf = (ages[-1] - start) / HORIZON_REF
        cap = CAP_BASE + CAP_SLOPE * hf
        floor = 0.0
        if source == "ghe":
            floor = GHE_FLOOR_BASE + GHE_FLOOR_SLOPE * hf
            cap = GHE_CAP_MULT * cap
        end = None if start == max(ages) else start + 4
        for i, gid in enumerate(union):
            p = float(pi_pt[i])
            if p <= 0:
                continue
            half = (float(hi[i]) - float(lo[i])) / 2.0
            rel = min(max(half / p, floor), cap)
            half = min(rel * p, ABS_HALF_CAP)
            rows.append((start, end, gid, p, max(0.0, p - half), min(1.0, p + half)))
    return rows

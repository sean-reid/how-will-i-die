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


def _cause_band(lt_age: int) -> int:
    # The two infant life-table bands share the 0-4 cause composition.
    return 0 if lt_age in (0, 1) else lt_age


def _damp(h: int, phi: float) -> float:
    return h if phi == 1 else (1 - phi**h) / (1 - phi)


def lifetime_causes(lc: LeeCarter, comp: Composition) -> list[tuple]:
    """Return (start_age, end_age, ghe_id, prob, prob_lo, prob_hi) rows."""
    ages = [int(x) for x in lc.ages]
    n_bands = len(ages)
    widths = [ages[i + 1] - ages[i] for i in range(n_bands - 1)] + [np.inf]

    union = sorted({int(g) for f in comp.bands.values() for g in f.ids})
    index = {gid: i for i, gid in enumerate(union)}

    rng = np.random.default_rng(SEED)
    draws = rng.normal(lc.drift, lc.drift_se, N_DRAWS)

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
            k_dr = lc.k[lc.jump] + draws * damp
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
            f = comp.frac_vector(_cause_band(ages[b]), diag_year, index)
            pi_pt += dd_pt * f
            pi_dr += dd_dr[:, None] * f[None, :]
            surv_pt *= 1.0 - q_pt
            surv_dr *= 1.0 - q_dr

        if abs(pi_pt.sum() - 1.0) > 1e-9:
            raise ValueError(f"lifetime shares do not sum to 1 (start {start}): {pi_pt.sum()}")

        lo = np.percentile(pi_dr, 5, axis=0)
        hi = np.percentile(pi_dr, 95, axis=0)
        end = None if start == max(ages) else start + 4
        for i, gid in enumerate(union):
            if pi_pt[i] > 0:
                rows.append((start, end, gid, float(pi_pt[i]), float(lo[i]), float(hi[i])))
    return rows

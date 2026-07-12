"""Validation of the projection: reconstruction, back-test, benchmarks, invariants.

Run as a script; prints a report and exits non-zero if a hard invariant fails.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from ..project.cohort import lifetime_causes
from ..project.composition import fit_composition
from ..project.lee_carter import fit_lee_carter
from ..project.run import project_all


def life_table_ex0(ages: list[int], mx: np.ndarray) -> float:
    """Reconstruct life expectancy at birth from abridged central death rates."""
    n = len(ages)
    width = [ages[i + 1] - ages[i] for i in range(n - 1)]
    lx = [1.0]
    big_l = []
    for i in range(n - 1):
        ax = 0.1 if ages[i] == 0 else 1.5 if ages[i] == 1 else width[i] / 2
        q = min(width[i] * mx[i] / (1 + (width[i] - ax) * mx[i]), 1.0)
        d = lx[i] * q
        lx.append(lx[i] - d)
        big_l.append(width[i] * lx[i + 1] + ax * d)
    big_l.append(lx[n - 1] / mx[n - 1] if mx[n - 1] > 0 else 0.0)  # open terminal band
    return sum(big_l) / lx[0]


def _subtree_ids(causes: pd.DataFrame, root: int) -> set[int]:
    parent = {int(r.ghe_id): int(r.parent_id) for r in causes.itertuples() if pd.notna(r.parent_id)}
    out = set()
    for cid in causes["ghe_id"].astype(int):
        cur = cid
        while cur is not None:
            if cur == root:
                out.add(int(cid))
                break
            cur = parent.get(cur)
    return out


def run(data_dir: Path) -> int:
    inter = data_dir / "intermediate"
    lt = pd.read_parquet(inter / "who_lifetables.parquet")
    cd = pd.read_parquet(inter / "cause_deaths.parquet")
    causes = pd.read_csv(Path(__file__).resolve().parents[3] / "mappings" / "ghe_causes.csv")
    failures = 0

    print("a. life-table reconstruction (reconstructed e0 vs WHO e0, 2019)")
    for iso in ["USA", "JPN", "GBR"]:
        for sex in ["male", "female"]:
            sub = lt[(lt.country_iso3 == iso) & (lt.sex == sex) & (lt.year == 2019)].sort_values(
                "age_start"
            )
            ages = [int(x) for x in sub.age_start]
            recon = life_table_ex0(ages, sub.mx.to_numpy())
            who = float(sub[sub.age_start == 0].ex.iloc[0])
            print(f"   {iso} {sex}: recon {recon:.2f}  who {who:.2f}  diff {recon - who:+.2f}")

    print("b. back-test (fit 2000-2015, forecast 2016-2019)")
    fit_years = list(range(2000, 2016))
    for iso in ["USA", "JPN"]:
        for sex in ["male", "female"]:
            sub = lt[(lt.country_iso3 == iso) & (lt.sex == sex)]
            lc = fit_lee_carter(sub[["year", "age_start", "mx"]], fit_years)
            ages = sorted(sub.age_start.unique())
            errs, e0e = [], []
            for yr in range(2016, 2020):
                actual = sub[sub.year == yr].sort_values("age_start").mx.to_numpy()
                fore = lc.mx_vector(yr)
                errs.append(np.mean(np.abs(fore - actual) / actual))
                e0e.append(
                    life_table_ex0([int(a) for a in ages], fore)
                    - life_table_ex0([int(a) for a in ages], actual)
                )
            mape = np.mean(errs) * 100
            print(f"   {iso} {sex}: mx MAPE {mape:.1f}%  e0 error {np.mean(e0e):+.2f} yr")

    print("c. lifetime-risk benchmark (USA, cohort from age 0)")
    cancer = _subtree_ids(causes, 610)
    cvd = _subtree_ids(causes, 1100)
    for sex in ["male", "female"]:
        lc = fit_lee_carter(
            lt[(lt.country_iso3 == "USA") & (lt.sex == sex)][["year", "age_start", "mx"]],
            list(range(2000, 2020)),
        )
        comp = fit_composition(
            cd[(cd.iso3 == "USA") & (cd.sex == sex)][["year", "age_start", "ghe_id", "deaths"]],
            list(range(2000, 2020)),
        )
        rows = [r for r in lifetime_causes(lc, comp) if r[0] == 0]
        pc = sum(r[3] for r in rows if r[2] in cancer)
        pv = sum(r[3] for r in rows if r[2] in cvd)
        print(f"   USA {sex}: cancer {pc * 100:.1f}%  cardiovascular {pv * 100:.1f}%")

    print("d. invariants across the full output")
    out = project_all(lt, cd)
    sums = out.groupby(["iso3", "sex", "start_age_start"])["prob"].sum()
    max_dev = float((sums - 1.0).abs().max())
    print(f"   max |sum(prob) - 1| = {max_dev:.2e}")
    if max_dev > 1e-6:
        failures += 1
    if not out["prob"].between(0, 1).all():
        print("   FAIL: probabilities outside [0, 1]")
        failures += 1
    print(f"   rows: {len(out)}")
    return failures


def main() -> None:
    import sys

    sys.exit(run(Path("../data")))


if __name__ == "__main__":
    main()

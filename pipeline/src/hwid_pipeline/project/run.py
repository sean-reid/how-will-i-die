"""Run the projection for every country and sex, write the lifetime lookup.

Reads the committed intermediate, fits Lee-Carter and the cause composition per
country and sex, integrates the cohort life table, and writes one tidy table of
lifetime cause probabilities. Deterministic; Phase 3 shards this to the site.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from .cohort import lifetime_causes
from .composition import fit_composition
from .lee_carter import FIT_YEARS, fit_lee_carter

# The seven registration countries use the MDB fine-age cause split; every other
# country uses the GHE country split.
MDB_COUNTRIES = ["USA", "GBR", "DEU", "FRA", "JPN", "CAN", "AUS"]
SEXES = ["male", "female"]
# GHE country files exist only for these years (uneven spacing is handled by the
# composition fit); the COVID years are excluded as trend anchors, matching the
# life-table Lee-Carter window.
GHE_FIT_YEARS = [2000, 2010, 2015, 2019]
COLUMNS = [
    "iso3",
    "sex",
    "start_age_start",
    "start_age_end",
    "ghe_id",
    "prob",
    "prob_lo",
    "prob_hi",
    "source",
]


def project_all(
    life_tables: pd.DataFrame,
    cause_deaths: pd.DataFrame,
    ghe_cause_deaths: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Project lifetime cause shares for every available country.

    The seven MDB countries use the registered fine-age cause split; the rest use
    the GHE country split (coarse bands, wider intervals). With
    ``ghe_cause_deaths=None`` only the seven MDB countries are projected, which
    keeps the original 7-country result bit-for-bit identical.
    """
    lt_iso = set(life_tables["country_iso3"])
    # MDB (fine detail) is the default for every country present in cause_deaths;
    # GHE (coarse) fills only the countries MDB does not cover.
    mdb_iso = sorted(set(cause_deaths["iso3"]) & lt_iso)
    plan = [(iso, "mdb") for iso in mdb_iso]
    if ghe_cause_deaths is not None:
        ghe_iso = sorted((set(ghe_cause_deaths["iso3"]) & lt_iso) - set(mdb_iso))
        plan += [(iso, "ghe") for iso in ghe_iso]

    rows = []
    skipped = []
    for iso, source in plan:
        splits = cause_deaths if source == "mdb" else ghe_cause_deaths
        comp_years = FIT_YEARS if source == "mdb" else GHE_FIT_YEARS
        for sex in SEXES:
            lt = life_tables[(life_tables["country_iso3"] == iso) & (life_tables["sex"] == sex)][
                ["year", "age_start", "mx"]
            ]
            cd = splits[(splits["iso3"] == iso) & (splits["sex"] == sex)][
                ["year", "age_start", "ghe_id", "deaths"]
            ]
            if lt.empty or cd.empty:
                skipped.append((iso, sex, "no data"))
                continue
            try:
                lc = fit_lee_carter(lt, FIT_YEARS)
                comp = fit_composition(cd, comp_years)
                for start, end, gid, prob, lo, hi in lifetime_causes(lc, comp, source):
                    rows.append((iso, sex, start, end, int(gid), prob, lo, hi, source))
            except (np.linalg.LinAlgError, ValueError) as exc:
                skipped.append((iso, sex, str(exc)))
    if skipped:
        print(f"skipped {len(skipped)} country-sex fits: {skipped[:6]}")
    out = pd.DataFrame(rows, columns=COLUMNS)
    return out.sort_values(
        ["iso3", "sex", "start_age_start", "prob"], ascending=[True, True, True, False]
    ).reset_index(drop=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=Path("../data"))
    args = parser.parse_args()

    inter = args.data_dir / "intermediate"
    life_tables = pd.read_parquet(inter / "who_lifetables.parquet")
    cause_deaths = pd.read_parquet(inter / "cause_deaths.parquet")
    ghe_path = inter / "ghe_cause_deaths.parquet"
    ghe_cause_deaths = pd.read_parquet(ghe_path) if ghe_path.exists() else None

    out = project_all(life_tables, cause_deaths, ghe_cause_deaths)
    dest = args.data_dir / "raw/derived/lifetime_causes.parquet"
    dest.parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(dest, index=False)
    print(f"wrote {len(out)} rows to {dest}")


if __name__ == "__main__":
    main()

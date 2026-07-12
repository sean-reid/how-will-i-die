"""Run the projection for every country and sex, write the lifetime lookup.

Reads the committed intermediate, fits Lee-Carter and the cause composition per
country and sex, integrates the cohort life table, and writes one tidy table of
lifetime cause probabilities. Deterministic; Phase 3 shards this to the site.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from .cohort import lifetime_causes
from .composition import fit_composition
from .lee_carter import FIT_YEARS, fit_lee_carter

COUNTRIES = ["USA", "GBR", "DEU", "FRA", "JPN", "CAN", "AUS"]
SEXES = ["male", "female"]
COLUMNS = [
    "iso3",
    "sex",
    "start_age_start",
    "start_age_end",
    "ghe_id",
    "prob",
    "prob_lo",
    "prob_hi",
]


def project_all(life_tables: pd.DataFrame, cause_deaths: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for iso in COUNTRIES:
        for sex in SEXES:
            lt = life_tables[(life_tables["country_iso3"] == iso) & (life_tables["sex"] == sex)][
                ["year", "age_start", "mx"]
            ]
            cd = cause_deaths[(cause_deaths["iso3"] == iso) & (cause_deaths["sex"] == sex)][
                ["year", "age_start", "ghe_id", "deaths"]
            ]
            lc = fit_lee_carter(lt, FIT_YEARS)
            comp = fit_composition(cd, FIT_YEARS)
            for start, end, gid, prob, lo, hi in lifetime_causes(lc, comp):
                rows.append((iso, sex, start, end, int(gid), prob, lo, hi))
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

    out = project_all(life_tables, cause_deaths)
    dest = args.data_dir / "raw/derived/lifetime_causes.parquet"
    dest.parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(dest, index=False)
    print(f"wrote {len(out)} rows to {dest}")


if __name__ == "__main__":
    main()

"""Normalize MDB ICD-10 deaths into GHE cause deaths per cell.

Turns the raw MDB extract (deaths by detailed ICD-10 code) into deaths by GHE
cause, with garbage codes redistributed onto real causes so the cause split is
not distorted. The output is the composition side of the projection: for each
(country, year, sex, age band) the death count by GHE cause. Population is not
needed here because the projection uses these only as shares within a cell.

Redistribution is proportional within each cell, to a target set that depends
on the garbage type (from the GHE methods annex footnotes):
    ill_defined                  -> all Group I and II causes
    cardiovascular               -> cardiovascular causes
    cancer_unspecified_site      -> malignant neoplasm causes
    injury_undetermined_intent   -> injury (Group III) causes
If a cell has no deaths in the target set, the amount falls back to all causes
in the cell. Redistribution conserves the total death count.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from .cause_map import map_icd10

# MDB country code -> ISO3 for the v1 countries.
ISO3 = {
    2450: "USA",
    4308: "GBR",
    4085: "DEU",
    4080: "FRA",
    3160: "JPN",
    2090: "CAN",
    5020: "AUS",
}

FIT_YEARS = range(2000, 2022)  # 2000-2021, the window shared with the life tables
TOP_AGE_START = 85  # collapse 85-89, 90-94, 95+ into a single open 85+ band
TOP_AGE_END = 125

CANCER_ROOT = 610
CVD_ROOT = 1100


def _ancestors(cause_id: int, parent: dict[int, int]) -> set[int]:
    seen = set()
    cur = parent.get(cause_id)
    while cur is not None and cur not in seen:
        seen.add(cur)
        cur = parent.get(cur)
    return seen


def cause_metadata(mappings_dir: Path) -> dict[str, set[int]]:
    """Target cause sets for redistribution, keyed by garbage type."""
    causes = pd.read_csv(mappings_dir / "ghe_causes.csv")
    parent = {int(r.ghe_id): int(r.parent_id) for r in causes.itertuples() if pd.notna(r.parent_id)}
    group = {int(r.ghe_id): r.group for r in causes.itertuples()}

    ranges = pd.read_csv(mappings_dir / "icd10_to_ghe.csv")
    leaves = {int(x) for x in ranges["ghe_id"].dropna().unique()}

    def in_subtree(cause_id: int, root: int) -> bool:
        return cause_id == root or root in _ancestors(cause_id, parent)

    return {
        "leaves": leaves,
        "ill_defined": {c for c in leaves if group.get(c) in ("I", "II")},
        "cardiovascular": {c for c in leaves if in_subtree(c, CVD_ROOT)},
        "cancer_unspecified_site": {c for c in leaves if in_subtree(c, CANCER_ROOT)},
        "injury_undetermined_intent": {c for c in leaves if group.get(c) == "III"},
    }


def _cap_age(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    top = df["age_start"] >= TOP_AGE_START
    df.loc[top, "age_start"] = TOP_AGE_START
    df.loc[top, "age_end"] = TOP_AGE_END
    return df


def _classify_codes(codes: pd.Index) -> pd.DataFrame:
    rows = []
    for code in codes:
        m = map_icd10(str(code))
        rows.append((code, m.ghe_id, m.is_garbage, m.garbage_type))
    return pd.DataFrame(rows, columns=["icd10", "ghe_id", "is_garbage", "garbage_type"])


CELL = ["iso3", "year", "sex", "age_start", "age_end"]


def _redistribute(
    real: pd.DataFrame, garbage: pd.DataFrame, targets: dict[str, set[int]]
) -> pd.DataFrame:
    """Add each cell's garbage deaths to the target causes, pro-rata by real deaths."""
    out = real.copy()
    for gtype, target_ids in (
        (t, targets[t])
        for t in [
            "ill_defined",
            "cardiovascular",
            "cancer_unspecified_site",
            "injury_undetermined_intent",
        ]
    ):
        chunk = garbage[garbage["garbage_type"] == gtype]
        if chunk.empty:
            continue
        for cell, amount in chunk.groupby(CELL, observed=True)["deaths"].sum().items():
            if amount <= 0:
                continue
            in_cell = out[
                (out["iso3"] == cell[0])
                & (out["year"] == cell[1])
                & (out["sex"] == cell[2])
                & (out["age_start"] == cell[3])
                & (out["age_end"] == cell[4])
            ]
            pool = in_cell[in_cell["ghe_id"].isin(target_ids)]
            if pool["deaths"].sum() <= 0:
                pool = in_cell  # fallback: spread across every cause in the cell
            if pool["deaths"].sum() <= 0:
                continue
            weights = pool["deaths"] / pool["deaths"].sum()
            out.loc[weights.index, "deaths"] = out.loc[weights.index, "deaths"] + amount * weights
    return out


def normalize_causes(mdb: pd.DataFrame, mappings_dir: Path) -> pd.DataFrame:
    """MDB tidy deaths -> GHE cause deaths per cell, garbage redistributed."""
    mdb = mdb[mdb["year"].isin(FIT_YEARS)].copy()
    mdb["iso3"] = mdb["country_code"].map(ISO3)
    mdb = mdb[mdb["iso3"].notna()]
    mdb = _cap_age(mdb)

    classified = _classify_codes(pd.Index(mdb["icd10"].unique()))
    mdb = mdb.merge(classified, on="icd10", how="left")

    total_before = mdb["deaths"].sum()

    real = (
        mdb[~mdb["is_garbage"] & mdb["ghe_id"].notna()]
        .groupby([*CELL, "ghe_id"], observed=True, as_index=False)["deaths"]
        .sum()
    )
    real["ghe_id"] = real["ghe_id"].astype(int)
    real["deaths"] = real["deaths"].astype(float)  # redistribution adds fractional amounts
    garbage = (
        mdb[mdb["is_garbage"]]
        .groupby([*CELL, "garbage_type"], observed=True, as_index=False)["deaths"]
        .sum()
    )

    targets = cause_metadata(mappings_dir)
    out = _redistribute(real, garbage, targets)

    total_after = out["deaths"].sum()
    if abs(total_after - total_before) > max(1.0, 1e-6 * total_before):
        raise ValueError(f"redistribution did not conserve deaths: {total_before} -> {total_after}")
    return out.sort_values([*CELL, "ghe_id"]).reset_index(drop=True)


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=Path("../data"))
    parser.add_argument("--mappings", type=Path, default=Path("mappings"))
    args = parser.parse_args()

    mdb = pd.read_parquet(args.data_dir / "raw/who/mdb/extract/mdb_icd10_deaths.parquet")
    out = normalize_causes(mdb, args.mappings)
    dest = args.data_dir / "intermediate/cause_deaths.parquet"
    dest.parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(dest, index=False)
    print(f"wrote {len(out)} rows to {dest}")


if __name__ == "__main__":
    main()

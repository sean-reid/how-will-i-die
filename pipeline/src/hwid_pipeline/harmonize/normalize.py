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

from ..ingest import mdb
from .cause_map import map_icd10


def load_iso3(mappings_dir: Path) -> dict[int, str]:
    """MDB numeric country code -> ISO3, from the committed crosswalk."""
    cw = pd.read_csv(Path(mappings_dir) / "mdb_iso3.csv")
    return {int(r.mdb_code): r.iso3 for r in cw.itertuples()}


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

# Garbage types are applied in this fixed order; each uses the running totals so
# the semantics match a per-cell sequential redistribution exactly.
GARBAGE_ORDER = [
    "ill_defined",
    "cardiovascular",
    "cancer_unspecified_site",
    "injury_undetermined_intent",
]


def _apply_type(out: pd.DataFrame, amount: pd.DataFrame, target_ids: set[int]) -> pd.DataFrame:
    """Distribute each cell's garbage ``amount`` over its target causes, pro-rata.

    Vectorized across all cells at once. Within a cell the amount is split in
    proportion to the current deaths of the target causes; if the target pool is
    empty it falls back to every cause in the cell. Equivalent to looping cell by
    cell, but fast enough for ~100 countries.
    """
    in_target = out["ghe_id"].isin(target_ids)
    pool_t = out[in_target].groupby(CELL, as_index=False, observed=True)["deaths"].sum()
    pool_t = pool_t.rename(columns={"deaths": "pool_t"})
    pool_a = out.groupby(CELL, as_index=False, observed=True)["deaths"].sum()
    pool_a = pool_a.rename(columns={"deaths": "pool_a"})

    cells = amount.merge(pool_t, on=CELL, how="left").merge(pool_a, on=CELL, how="left")
    cells[["pool_t", "pool_a"]] = cells[["pool_t", "pool_a"]].fillna(0.0)
    cells["fallback"] = cells["pool_t"] <= 0
    cells["denom"] = cells["pool_t"].where(~cells["fallback"], cells["pool_a"])
    cells = cells[cells["denom"] > 0]
    if cells.empty:
        return out

    merged = out.merge(cells[[*CELL, "amount", "denom", "fallback"]], on=CELL, how="left")
    receives = merged["amount"].notna() & (merged["fallback"] | merged["ghe_id"].isin(target_ids))
    add = (merged["amount"] * merged["deaths"] / merged["denom"]).where(receives, 0.0)
    merged["deaths"] = merged["deaths"] + add.fillna(0.0)
    return merged[[*CELL, "ghe_id", "deaths"]]


def _redistribute(
    real: pd.DataFrame, garbage: pd.DataFrame, targets: dict[str, set[int]]
) -> pd.DataFrame:
    """Add each cell's garbage deaths to the target causes, pro-rata by real deaths."""
    out = real.copy()
    if garbage.empty:
        return out
    for gtype in GARBAGE_ORDER:
        amount = (
            garbage[garbage["garbage_type"] == gtype]
            .groupby(CELL, as_index=False, observed=True)["deaths"]
            .sum()
            .rename(columns={"deaths": "amount"})
        )
        amount = amount[amount["amount"] > 0]
        if amount.empty:
            continue
        out = _apply_type(out, amount, targets[gtype])
    return out


def normalize_causes(mdb: pd.DataFrame, mappings_dir: Path) -> pd.DataFrame:
    """MDB tidy deaths -> GHE cause deaths per cell, garbage redistributed."""
    mdb = mdb[mdb["year"].isin(FIT_YEARS)].copy()
    mdb["iso3"] = mdb["country_code"].map(load_iso3(mappings_dir))
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


def _class_maps(causes: pd.Index) -> tuple[dict, dict, dict]:
    """Build cause-code -> (ghe_id, is_garbage, garbage_type) lookup dicts."""
    ghe, garb, gtype = {}, {}, {}
    for code in causes:
        m = map_icd10(str(code))
        ghe[code], garb[code], gtype[code] = m.ghe_id, m.is_garbage, m.garbage_type
    return ghe, garb, gtype


_BAND_COLS = list(mdb.AGE_BANDS)


def _aggregate_wide(wide: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Sum the wide age columns per (country, year, sex, cause class).

    Classifies each ICD-10 code, then aggregates the death columns without
    melting first, so the row count stays bounded no matter how many countries
    are included. Returns (real_wide, garbage_wide), still wide over age columns.
    """
    ghe, garb, gtype = _class_maps(pd.Index(wide["Cause"].unique()))
    wide = wide.copy()
    wide["ghe_id"] = wide["Cause"].map(ghe)
    wide["is_garbage"] = wide["Cause"].map(garb)
    wide["garbage_type"] = wide["Cause"].map(gtype)
    for col in _BAND_COLS:
        wide[col] = pd.to_numeric(wide[col], errors="coerce").fillna(0.0)

    real = (
        wide[(~wide["is_garbage"]) & wide["ghe_id"].notna()]
        .groupby(["Country", "Year", "Sex", "ghe_id"], as_index=False)[_BAND_COLS]
        .sum()
    )
    garbage = (
        wide[wide["is_garbage"]]
        .groupby(["Country", "Year", "Sex", "garbage_type"], as_index=False)[_BAND_COLS]
        .sum()
    )
    return real, garbage


def _wide_to_tidy(agg: pd.DataFrame, key: str, iso3_map: dict[int, str]) -> pd.DataFrame:
    """Melt an aggregated wide frame to tidy cells, capping the top age band."""
    long = agg.melt(
        id_vars=["Country", "Year", "Sex", key],
        value_vars=_BAND_COLS,
        var_name="death_col",
        value_name="deaths",
    )
    bands = long["death_col"].map(mdb.AGE_BANDS)
    long["age_start"] = bands.str[0]
    long["age_end"] = bands.str[1]
    top = long["age_start"] >= TOP_AGE_START
    long.loc[top, "age_start"] = TOP_AGE_START
    long.loc[top, "age_end"] = TOP_AGE_END
    long["iso3"] = long["Country"].map(iso3_map)
    long["sex"] = long["Sex"].map(mdb.SEX_LABELS)
    long["year"] = long["Year"].astype(int)
    long = long[long["iso3"].notna() & long["sex"].notna() & long["year"].isin(FIT_YEARS)]
    tidy = long.groupby([*CELL, key], as_index=False, observed=True)["deaths"].sum()
    tidy["deaths"] = tidy["deaths"].astype(float)
    return tidy


def build_cause_deaths_from_parts(data_dir: Path, mappings_dir: Path) -> pd.DataFrame:
    """Build the MDB cause-deaths table for every crosswalked country.

    Streams the cached ICD-10 part files, aggregating each to GHE causes before
    melting so memory stays bounded, then redistributes garbage codes across all
    cells at once. Returns tidy (iso3, year, sex, age band, ghe_id, deaths).
    """
    iso3_map = load_iso3(mappings_dir)
    codes = tuple(iso3_map)
    parts_dir = Path(data_dir) / "raw/who/mdb/parts"

    real_parts, garbage_parts = [], []
    for n in mdb.PART_NUMBERS:
        zip_path = mdb.download_part(n, parts_dir)
        csv_path = mdb.extract_part_csv(zip_path, parts_dir)
        try:
            wide = mdb.read_country_rows(csv_path, codes)
            if wide.empty:
                continue
            wide = mdb._drop_duplicate_lists(wide)
            rw, gw = _aggregate_wide(wide)
            real_parts.append(rw)
            garbage_parts.append(gw)
        finally:
            csv_path.unlink(missing_ok=True)

    real_wide = (
        pd.concat(real_parts, ignore_index=True)
        .groupby(["Country", "Year", "Sex", "ghe_id"], as_index=False)[_BAND_COLS]
        .sum()
    )
    garbage_wide = (
        pd.concat(garbage_parts, ignore_index=True)
        .groupby(["Country", "Year", "Sex", "garbage_type"], as_index=False)[_BAND_COLS]
        .sum()
    )

    real = _wide_to_tidy(real_wide, "ghe_id", iso3_map)
    real["ghe_id"] = real["ghe_id"].astype(int)
    garbage = _wide_to_tidy(garbage_wide, "garbage_type", iso3_map)

    total_before = real["deaths"].sum() + garbage["deaths"].sum()
    out = _redistribute(real, garbage, cause_metadata(mappings_dir))
    if abs(out["deaths"].sum() - total_before) > max(1.0, 1e-6 * total_before):
        raise ValueError(
            f"redistribution did not conserve deaths: {total_before} -> {out['deaths'].sum()}"
        )
    return out.sort_values([*CELL, "ghe_id"]).reset_index(drop=True)


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=Path("../data"))
    parser.add_argument("--mappings", type=Path, default=Path("mappings"))
    args = parser.parse_args()

    out = build_cause_deaths_from_parts(args.data_dir, args.mappings)
    dest = args.data_dir / "intermediate/cause_deaths.parquet"
    dest.parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(dest, index=False)
    print(f"wrote {len(out)} rows, {out['iso3'].nunique()} countries to {dest}")


if __name__ == "__main__":
    main()

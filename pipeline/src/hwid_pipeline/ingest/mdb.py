"""Reader for the WHO Mortality Database (MDB), ICD-10 detailed files.

The MDB ships registered death counts by country, year, sex, ICD-10 cause and
5-year age band. We only need it for the cause split (each cause's share of
deaths within an age/sex/year cell); survival comes from the WHO life tables in
a separate reader, so population is not read here.

The raw data is split across six zipped part files on the WHO CDN, each holding
a single fixed-width-column CSV (first row = field names). This module can
download a part, extract it, filter it down to the countries we care about, and
melt the wide age columns into tidy long rows. To keep disk use bounded, the
build_extract driver deletes each raw part CSV before moving to the next part.
"""

from __future__ import annotations

import urllib.request
import zipfile
from pathlib import Path

import pandas as pd

# MDB country codes for the seven countries the project covers. The UK reports
# national totals under 4308; the England&Wales / N.Ireland / Scotland
# subnational codes are only needed if 4308 ever lacks national rows.
COUNTRY_CODES: tuple[int, ...] = (
    2450,  # United States
    4308,  # United Kingdom
    4085,  # Germany
    4080,  # France
    3160,  # Japan
    2090,  # Canada
    5020,  # Australia
)

# ICD-10 detailed list codes. 10M is the combined 3-char + 4-char detailed list;
# 103 is the 3-char detailed list; 104 is the 4-char detailed list. A given
# country-year reports in one of these. 101 (Mortality Tabulation List 1) is a
# condensed list and is excluded.
DETAILED_LISTS: tuple[str, ...] = ("10M", "104", "103")

# Preference order when, unexpectedly, more than one detailed list shows up for
# the same country-year: keep the most complete single list and drop the rest so
# deaths are not double counted.
_LIST_PREFERENCE = {code: rank for rank, code in enumerate(DETAILED_LISTS)}

# The detailed files carry an "all causes" rollup under cause code AAA whose
# count equals the sum of every leaf code in the same cell. It is dropped so the
# extract holds only mutually exclusive detailed causes; leaving it in would
# double every cause-share denominator downstream.
ALL_CAUSES_CODE = "AAA"

PART_URL = (
    "https://cdn.who.int/media/docs/default-source/world-health-data-platform/"
    "mortality-raw-data/morticd10_part{n}.zip"
)
PART_NUMBERS: tuple[int, ...] = (1, 2, 3, 4, 5, 6)

# The CDN rejects requests without a browser-like User-Agent (HTTP 403).
_USER_AGENT = "Mozilla/5.0 (compatible; hwid-pipeline/0.1)"

# Deaths<k> column -> (age_start, age_end) inclusive. Deaths2..Deaths6 are the
# single-year 0,1,2,3,4 columns; they collapse into one 0-4 band. Deaths7..25 are
# already 5-year bands. Deaths1 (all ages), Deaths26 (unspecified age) and the
# IM_* infant columns are not age bands and are dropped from the tidy output.
AGE_BANDS: dict[str, tuple[int, int]] = {
    "Deaths2": (0, 4),
    "Deaths3": (0, 4),
    "Deaths4": (0, 4),
    "Deaths5": (0, 4),
    "Deaths6": (0, 4),
    "Deaths7": (5, 9),
    "Deaths8": (10, 14),
    "Deaths9": (15, 19),
    "Deaths10": (20, 24),
    "Deaths11": (25, 29),
    "Deaths12": (30, 34),
    "Deaths13": (35, 39),
    "Deaths14": (40, 44),
    "Deaths15": (45, 49),
    "Deaths16": (50, 54),
    "Deaths17": (55, 59),
    "Deaths18": (60, 64),
    "Deaths19": (65, 69),
    "Deaths20": (70, 74),
    "Deaths21": (75, 79),
    "Deaths22": (80, 84),
    "Deaths23": (85, 89),
    "Deaths24": (90, 94),
    "Deaths25": (95, 125),  # open-ended 95+ band
}

SEX_LABELS = {1: "male", 2: "female"}

TIDY_COLUMNS = (
    "country_code",
    "year",
    "sex",
    "age_start",
    "age_end",
    "icd10",
    "deaths",
)


def part_url(n: int) -> str:
    return PART_URL.format(n=n)


def download_part(n: int, parts_dir: Path) -> Path:
    """Download part ``n`` into ``parts_dir`` and return the zip path.

    Skips the download if the zip already exists so reruns are cheap.
    """
    parts_dir.mkdir(parents=True, exist_ok=True)
    zip_path = parts_dir / f"morticd10_part{n}.zip"
    if not zip_path.exists():
        request = urllib.request.Request(part_url(n), headers={"User-Agent": _USER_AGENT})
        with urllib.request.urlopen(request) as response:
            zip_path.write_bytes(response.read())
    return zip_path


def extract_part_csv(zip_path: Path, parts_dir: Path) -> Path:
    """Extract the single CSV member from ``zip_path`` and return its path."""
    with zipfile.ZipFile(zip_path) as zf:
        members = zf.namelist()
        if len(members) != 1:
            raise ValueError(f"expected one member in {zip_path.name}, found {members}")
        member = members[0]
        zf.extract(member, parts_dir)
    return parts_dir / member


def read_country_rows(
    csv_path: Path,
    country_codes: tuple[int, ...] = COUNTRY_CODES,
) -> pd.DataFrame:
    """Read one part CSV and keep national detailed-ICD-10 rows for our countries.

    Filters applied: country in ``country_codes``, national level only
    (Admin1 and SubDiv blank), List in the detailed set, and Sex in {1, 2}. The
    returned frame is still wide (one row per country/year/list/cause/sex with
    the Deaths columns intact).
    """
    death_cols = [f"Deaths{k}" for k in range(1, 27)]
    usecols = ["Country", "Admin1", "SubDiv", "Year", "List", "Cause", "Sex", "Frmat", *death_cols]
    dtype = {
        "Country": "int64",
        "Admin1": "string",
        "SubDiv": "string",
        "Year": "int64",
        "List": "string",
        "Cause": "string",
        "Sex": "int64",
        "Frmat": "string",
    }
    frames = []
    for chunk in pd.read_csv(
        csv_path,
        usecols=usecols,
        dtype=dtype,
        chunksize=200_000,
    ):
        keep = (
            chunk["Country"].isin(country_codes)
            & chunk["Admin1"].isna()
            & chunk["SubDiv"].isna()
            & chunk["List"].isin(DETAILED_LISTS)
            & chunk["Sex"].isin(SEX_LABELS)
            & (chunk["Cause"] != ALL_CAUSES_CODE)
        )
        subset = chunk.loc[keep]
        if not subset.empty:
            frames.append(subset.copy())
    if not frames:
        return pd.DataFrame(columns=usecols)
    return pd.concat(frames, ignore_index=True)


def _drop_duplicate_lists(df: pd.DataFrame) -> pd.DataFrame:
    """Keep a single preferred detailed list per country-year.

    Normally a country-year uses exactly one list, so this is a no-op. When more
    than one detailed list is present we keep the most complete (see
    ``DETAILED_LISTS``) to avoid summing overlapping counts.
    """
    lists_per_year = df.groupby(["Country", "Year"])["List"].nunique()
    multi = lists_per_year[lists_per_year > 1].index
    if len(multi) == 0:
        return df
    rank = df["List"].map(_LIST_PREFERENCE)
    chosen = (
        df.assign(_rank=rank)
        .sort_values("_rank")
        .groupby(["Country", "Year"], as_index=False)["List"]
        .first()
        .rename(columns={"List": "_keep_list"})
    )
    merged = df.merge(chosen, on=["Country", "Year"], how="left")
    return merged.loc[merged["List"] == merged["_keep_list"]].drop(columns="_keep_list")


def melt_deaths(df: pd.DataFrame) -> pd.DataFrame:
    """Melt the wide age columns of a filtered frame into tidy long rows.

    Returns columns ``country_code, year, sex, age_start, age_end, icd10,
    deaths``. Deaths2..Deaths6 collapse into the single 0-4 band; sex is mapped
    to 'male'/'female'.
    """
    if df.empty:
        return pd.DataFrame(columns=TIDY_COLUMNS)

    df = _drop_duplicate_lists(df)

    band_cols = list(AGE_BANDS)
    long = df.melt(
        id_vars=["Country", "Year", "Sex", "Cause"],
        value_vars=band_cols,
        var_name="death_col",
        value_name="deaths",
    )
    long["deaths"] = pd.to_numeric(long["deaths"], errors="coerce").fillna(0).astype("int64")

    bands = long["death_col"].map(AGE_BANDS)
    long["age_start"] = bands.str[0]
    long["age_end"] = bands.str[1]

    long["sex"] = long["Sex"].map(SEX_LABELS)
    long = long.rename(columns={"Country": "country_code", "Year": "year", "Cause": "icd10"})

    # Sum within band so the collapsed Deaths2..Deaths6 land in one 0-4 row.
    tidy = long.groupby(
        ["country_code", "year", "sex", "age_start", "age_end", "icd10"],
        as_index=False,
    )["deaths"].sum()
    return tidy[list(TIDY_COLUMNS)]


def build_extract(
    data_dir: Path,
    part_numbers: tuple[int, ...] = PART_NUMBERS,
    keep_part_csv: bool = False,
) -> Path:
    """Download, filter and melt every part, writing one tidy parquet extract.

    ``data_dir`` is the ``data/raw/who/mdb`` directory. Parts are downloaded to
    ``<data_dir>/parts`` and the extract is written to
    ``<data_dir>/extract/mdb_icd10_deaths.parquet``. Each raw part CSV is deleted
    after filtering (unless ``keep_part_csv``) to bound disk use.
    """
    parts_dir = data_dir / "parts"
    extract_dir = data_dir / "extract"
    extract_dir.mkdir(parents=True, exist_ok=True)

    tidy_frames = []
    for n in part_numbers:
        zip_path = download_part(n, parts_dir)
        csv_path = extract_part_csv(zip_path, parts_dir)
        try:
            wide = read_country_rows(csv_path)
            tidy_frames.append(melt_deaths(wide))
        finally:
            if not keep_part_csv:
                csv_path.unlink(missing_ok=True)

    extract = (
        pd.concat(tidy_frames, ignore_index=True)
        if tidy_frames
        else pd.DataFrame(columns=TIDY_COLUMNS)
    )
    extract = extract.sort_values(list(TIDY_COLUMNS)).reset_index(drop=True)

    out_path = extract_dir / "mdb_icd10_deaths.parquet"
    extract.to_parquet(out_path, index=False)
    return out_path


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path("../data/raw/who/mdb"),
        help="the data/raw/who/mdb directory",
    )
    parser.add_argument("--keep-part-csv", action="store_true")
    args = parser.parse_args()
    out = build_extract(args.data_dir, keep_part_csv=args.keep_part_csv)
    print(f"wrote {out}")


if __name__ == "__main__":
    main()

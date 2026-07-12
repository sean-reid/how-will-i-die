"""Reader for WHO GHE 2021 country-level deaths by cause, age and sex.

This is the country analogue of the WHO-region summary workbook. It is the
Phase 4 cause-split backbone: it gives, for every WHO member state, the number
of deaths by GHE cause within coarse age bands, from which the site derives each
cause's SHARE of deaths in an age/sex cell (the survival side comes from the WHO
GHO life tables in ``lifetable.py``; population is not needed because the split
is a ratio).

Source files (one workbook per reference year), WHO GHO CDN:

    2000  ghe2021_deaths_bycountry_2000.xlsx
    2010  ghe2021_deaths_bycountry_age_sex_2010_new.xlsx
    2015  ghe2021_deaths_bycountry_2015.xlsx
    2019  ghe2021_deaths_bycountry_2019.xlsx
    2020  ghe2021_deaths_bycountry_2020.xlsx
    2021  ghe2021_deaths_bycountry_2021.xlsx

all under
    https://cdn.who.int/media/docs/default-source/gho-documents/global-health-estimates/

Workbook layout (verified against the 2021 file): one sheet per coarse age band
(``0-4``, ``5-14``, ``15-29``, ``30-49``, ``50-59``, ``60-69``, ``70+``) plus a
``Notes`` and an ``All ages`` sheet that this reader ignores. In every age sheet
countries are laid out across columns (185 member states, ISO-3 codes on row
index 7, starting at column index 7) and rows are stacked in three sex blocks
(Persons, then Males, then Females). Column 0 carries the sex label on every data
row, column 1 carries the GHE cause code, and the leading rows of each block are
a Population row (blank code) and an All Causes rollup (code 0), both dropped
here. Deaths are published in thousands; cause SHARES are unit-invariant so this
does not matter downstream.

Coarse, uneven age bands are the defining constraint of the country GHE data
(the region workbook additionally splits 0-4 into 0-28 days and 1-59 months; the
country workbook does not). See ``project/PHASE4_NOTES.md`` for how these bands
are meant to be graduated onto the finer life-table grid.
"""

from __future__ import annotations

import urllib.request
from pathlib import Path

import pandas as pd

_CDN_BASE = "https://cdn.who.int/media/docs/default-source/gho-documents/global-health-estimates"

# Reference year -> country workbook file name on the WHO CDN. The naming is not
# uniform across years (2010 carries an extra suffix); this map pins the exact
# names so callers do not have to guess.
BYCOUNTRY_FILES: dict[int, str] = {
    2000: "ghe2021_deaths_bycountry_2000.xlsx",
    2010: "ghe2021_deaths_bycountry_age_sex_2010_new.xlsx",
    2015: "ghe2021_deaths_bycountry_2015.xlsx",
    2019: "ghe2021_deaths_bycountry_2019.xlsx",
    2020: "ghe2021_deaths_bycountry_2020.xlsx",
    2021: "ghe2021_deaths_bycountry_2021.xlsx",
}

# The CDN rejects requests without a browser-like User-Agent (HTTP 403).
_USER_AGENT = "Mozilla/5.0 (compatible; hwid-pipeline/0.1)"

# Age-band sheet name -> (age_start, age_end). age_end is the EXCLUSIVE upper
# bound (matching the life-table reader's convention) and is None for the
# open-ended top band. These seven bands are the full published age resolution.
AGE_BANDS: dict[str, tuple[int, int | None]] = {
    "0-4": (0, 5),
    "5-14": (5, 15),
    "15-29": (15, 30),
    "30-49": (30, 50),
    "50-59": (50, 60),
    "60-69": (60, 70),
    "70+": (70, None),
}

# Sex block label -> project vocabulary. "Persons" is the both-sexes block.
SEX_LABELS: dict[str, str] = {
    "Persons": "both",
    "Males": "male",
    "Females": "female",
}

# Fixed cell geometry (0-based) shared by every age sheet.
_ISO_ROW = 7
_FIRST_COUNTRY_COL = 7
_SEX_COL = 0
_CODE_COL = 1

# All Causes rollup code; dropped so the extract holds only cause rows.
_ALL_CAUSES_CODE = 0

OUTPUT_COLUMNS = (
    "iso3",
    "sex",
    "age_start",
    "age_end",
    "ghe_cause_id",
    "year",
    "deaths",
)


def bycountry_url(year: int) -> str:
    """Return the WHO CDN download URL for the country workbook of ``year``."""
    try:
        return f"{_CDN_BASE}/{BYCOUNTRY_FILES[year]}"
    except KeyError as exc:
        raise ValueError(f"no country GHE workbook known for year {year}") from exc


def download_year(year: int, dest_dir: Path) -> Path:
    """Download the country workbook for ``year`` into ``dest_dir``.

    Skips the download if the file already exists so reruns are cheap and the
    WHO CDN is not hit twice.
    """
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    out_path = dest_dir / BYCOUNTRY_FILES[year]
    if not out_path.exists():
        request = urllib.request.Request(bycountry_url(year), headers={"User-Agent": _USER_AGENT})
        with urllib.request.urlopen(request) as response:
            out_path.write_bytes(response.read())
    return out_path


def load_ghe_ids(mappings_dir: Path) -> set[int]:
    """Load the set of GHE cause ids the project recognises."""
    causes = pd.read_csv(Path(mappings_dir) / "ghe_causes.csv")
    return set(causes["ghe_id"].astype(int))


def _country_columns(raw: pd.DataFrame) -> dict[int, str]:
    """Map each country data column index to its ISO-3 code."""
    iso_row = raw.iloc[_ISO_ROW, _FIRST_COUNTRY_COL:]
    return {
        col: value for col, value in iso_row.items() if isinstance(value, str) and len(value) == 3
    }


def read_age_sheet(
    xlsx_path: Path,
    sheet: str,
    ghe_ids: set[int],
    year: int,
) -> pd.DataFrame:
    """Read one age-band sheet into tidy long rows.

    Keeps only rows whose sex label is known and whose GHE code is present in
    ``ghe_ids`` (this drops the Population and All Causes rows and any GHE 2021
    sub-cause the project mapping does not carry; those sub-causes' deaths are
    still represented at their mapped parent code). Returns the shared output
    columns.
    """
    raw = pd.read_excel(xlsx_path, sheet_name=sheet, header=None)
    country_cols = _country_columns(raw)
    if not country_cols:
        raise ValueError(f"no ISO-3 country columns found on sheet {sheet!r}")

    sex = raw[_SEX_COL].map(SEX_LABELS)
    code = pd.to_numeric(raw[_CODE_COL], errors="coerce")
    keep = sex.notna() & code.notna() & code.astype("Int64").isin(ghe_ids)
    subset = raw.loc[keep, [_SEX_COL, _CODE_COL, *country_cols]]
    if subset.empty:
        return pd.DataFrame(columns=OUTPUT_COLUMNS)

    long = subset.melt(
        id_vars=[_SEX_COL, _CODE_COL],
        value_vars=list(country_cols),
        var_name="_col",
        value_name="deaths",
    )
    long["iso3"] = long["_col"].map(country_cols)
    long["sex"] = long[_SEX_COL].map(SEX_LABELS)
    long["ghe_cause_id"] = pd.to_numeric(long[_CODE_COL]).astype("int64")
    long["deaths"] = pd.to_numeric(long["deaths"], errors="coerce").fillna(0.0)

    age_start, age_end = AGE_BANDS[sheet]
    long["age_start"] = age_start
    long["age_end"] = age_end
    long["year"] = year
    return long[list(OUTPUT_COLUMNS)]


def normalize(xlsx_path: Path, year: int, ghe_ids: set[int]) -> pd.DataFrame:
    """Normalize every age sheet in one country workbook to tidy long rows.

    Returns one row per (iso3, sex, age band, GHE cause) with a deaths value,
    sorted deterministically on the key columns.
    """
    frames = [read_age_sheet(xlsx_path, sheet, ghe_ids, year) for sheet in AGE_BANDS]
    tidy = pd.concat(frames, ignore_index=True)
    sort_keys = ["iso3", "sex", "age_start", "ghe_cause_id"]
    tidy = tidy.sort_values(sort_keys, kind="stable").reset_index(drop=True)
    return tidy[list(OUTPUT_COLUMNS)]


def build_extract(
    data_dir: Path,
    mappings_dir: Path,
    years: tuple[int, ...] = (2021,),
) -> Path:
    """Download, normalize and write the country GHE deaths extract.

    ``data_dir`` is the ``data/raw/who/ghe-country`` directory; workbooks are
    downloaded there and the extract is written to
    ``<data_dir>/extract/ghe_country_deaths.parquet``. Defaults to 2021 (the
    most recent reference year) to avoid re-downloading every historical year.
    """
    data_dir = Path(data_dir)
    extract_dir = data_dir / "extract"
    extract_dir.mkdir(parents=True, exist_ok=True)
    ghe_ids = load_ghe_ids(mappings_dir)

    frames = []
    for year in years:
        xlsx_path = download_year(year, data_dir)
        frames.append(normalize(xlsx_path, year, ghe_ids))

    extract = pd.concat(frames, ignore_index=True)
    extract = extract.sort_values(
        ["year", "iso3", "sex", "age_start", "ghe_cause_id"], kind="stable"
    ).reset_index(drop=True)

    out_path = extract_dir / "ghe_country_deaths.parquet"
    extract.to_parquet(out_path, index=False)
    return out_path


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path("../data/raw/who/ghe-country"),
        help="the data/raw/who/ghe-country directory",
    )
    parser.add_argument(
        "--mappings-dir",
        type=Path,
        default=Path("mappings"),
        help="the pipeline mappings directory (holds ghe_causes.csv)",
    )
    parser.add_argument(
        "--years",
        type=int,
        nargs="+",
        default=[2021],
        help="reference years to include (default: 2021)",
    )
    args = parser.parse_args()
    out = build_extract(args.data_dir, args.mappings_dir, tuple(args.years))
    frame = pd.read_parquet(out)
    print(f"wrote {len(frame)} rows to {out}")
    print(f"countries: {frame['iso3'].nunique()}  causes: {frame['ghe_cause_id'].nunique()}")


if __name__ == "__main__":
    main()

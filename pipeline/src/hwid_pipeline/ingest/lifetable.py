"""Reader for WHO GHO life tables (GHE 2021, completeness-adjusted).

The GHO OData API exposes each life-table column as a separate indicator. This
reader loads the cached per-indicator JSON files, joins them on
(country, year, sex, age group), and returns tidy long rows.

Granularity is abridged 5-year age groups ([0,1), [1,5), [5,10), ..., 85+).
Years 2000-2021, sexes male / female / both. These are historical tables; WHO
does not publish projected future life tables through this product.

Usage:
    from hwid_pipeline.ingest.lifetable import load_lifetables
    df = load_lifetables(Path("../data/raw/who/lifetables"))
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

# GHO indicator code -> tidy column name.
INDICATOR_COLUMNS = {
    "LIFE_0000000029": "mx",  # nMx  age-specific death rate
    "LIFE_0000000030": "qx",  # nqx  probability of dying in interval
    "LIFE_0000000031": "lx",  # lx   survivors at age x
    "LIFE_0000000032": "dx",  # ndx  deaths in interval
    "LIFE_0000000033": "nLx",  # nLx  person-years lived in interval
    "LIFE_0000000034": "Tx",  # Tx   person-years lived above age x
    "LIFE_0000000035": "ex",  # ex   expectation of life at age x
}

# WHO sex codes mapped to the project vocabulary.
SEX_LABELS = {
    "SEX_MLE": "male",
    "SEX_FMLE": "female",
    "SEX_BTSX": "both",
}

# Abridged age breakpoints (interval starts). The upper bound of each interval
# is the next start; the final group (85+) is open-ended.
_AGE_BREAKS = [0, 1, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55, 60, 65, 70, 75, 80, 85]
_AGE_END = {start: _AGE_BREAKS[i + 1] for i, start in enumerate(_AGE_BREAKS[:-1])}
_AGE_END[_AGE_BREAKS[-1]] = None

_OUTPUT_COLUMNS = [
    "country_iso3",
    "year",
    "sex",
    "age_start",
    "age_end",
    "mx",
    "qx",
    "lx",
    "dx",
    "nLx",
    "Tx",
    "ex",
]


def parse_age_group(label: str) -> tuple[int, int | None]:
    """Parse a GHO age-group code into (age_start, age_end).

    age_end is the exclusive upper bound (start of the next abridged interval);
    it is None for the open-ended top group.

        'AGEGROUP_YEARS00-01' -> (0, 1)
        'AGEGROUP_YEARS01-04' -> (1, 5)
        'AGEGROUP_YEARS85PLUS' -> (85, None)
    """
    token = label.removeprefix("AGEGROUP_YEARS")
    if token.endswith("PLUS"):
        start = int(token.removesuffix("PLUS"))
        return start, None
    start = int(token.split("-")[0])
    if start not in _AGE_END:
        raise ValueError(f"unexpected age group start {start} in {label!r}")
    return start, _AGE_END[start]


def map_sex(code: str) -> str:
    """Map a GHO sex code to 'male' / 'female' / 'both'."""
    try:
        return SEX_LABELS[code]
    except KeyError as exc:
        raise ValueError(f"unexpected sex code {code!r}") from exc


def _load_indicator(path: Path, column: str) -> pd.DataFrame:
    """Load one indicator JSON into a long frame keyed on the shared dimensions."""
    with path.open() as fh:
        records = json.load(fh)["value"]
    rows = []
    for r in records:
        rows.append(
            {
                "country_iso3": r["SpatialDim"],
                "year": int(r["TimeDim"]),
                "sex": map_sex(r["Dim1"]),
                "age_label": r["Dim2"],
                column: r["NumericValue"],
            }
        )
    return pd.DataFrame(rows)


def load_lifetables(data_dir: Path) -> pd.DataFrame:
    """Load and normalize the cached WHO life-table indicators to tidy rows.

    Returns one row per (country_iso3, year, sex, age group) with the life-table
    columns mx, qx, lx, dx, nLx, Tx, ex. Deterministic: rows are sorted on the
    key columns and the column order is fixed.
    """
    data_dir = Path(data_dir)
    keys = ["country_iso3", "year", "sex", "age_label"]
    merged: pd.DataFrame | None = None
    for code, column in INDICATOR_COLUMNS.items():
        path = data_dir / f"{code}.json"
        if not path.exists():
            raise FileNotFoundError(f"missing life-table indicator file: {path}")
        frame = _load_indicator(path, column)
        merged = frame if merged is None else merged.merge(frame, on=keys, how="outer")

    if merged is None or merged.empty:
        raise ValueError(f"no life-table records found under {data_dir}")

    bounds = merged["age_label"].map(parse_age_group)
    merged["age_start"] = [b[0] for b in bounds]
    merged["age_end"] = [b[1] for b in bounds]

    merged = merged.sort_values(
        ["country_iso3", "year", "sex", "age_start"], kind="stable"
    ).reset_index(drop=True)
    return merged[_OUTPUT_COLUMNS]


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=Path("../data/raw/who/lifetables"))
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("../data/raw/who/lifetables/extract/who_lifetables.parquet"),
    )
    args = parser.parse_args()
    df = load_lifetables(args.data_dir)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(args.out, index=False)
    print(f"wrote {len(df)} rows to {args.out}")


if __name__ == "__main__":
    main()

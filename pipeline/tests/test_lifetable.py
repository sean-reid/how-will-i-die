"""Tests for the WHO life-table reader on a tiny inline fixture."""

import json
from pathlib import Path

from hwid_pipeline.ingest.lifetable import (
    INDICATOR_COLUMNS,
    load_lifetables,
    map_sex,
    parse_age_group,
)


def test_parse_age_group_bounds() -> None:
    assert parse_age_group("AGEGROUP_YEARS00-01") == (0, 1)
    assert parse_age_group("AGEGROUP_YEARS01-04") == (1, 5)
    assert parse_age_group("AGEGROUP_YEARS05-09") == (5, 10)
    assert parse_age_group("AGEGROUP_YEARS80-84") == (80, 85)
    assert parse_age_group("AGEGROUP_YEARS85PLUS") == (85, None)


def test_map_sex() -> None:
    assert map_sex("SEX_MLE") == "male"
    assert map_sex("SEX_FMLE") == "female"
    assert map_sex("SEX_BTSX") == "both"


# Three contiguous age groups for a single male country-year. lx must not
# increase as age rises (survivorship is monotonic non-increasing).
_AGES = ["AGEGROUP_YEARS00-01", "AGEGROUP_YEARS01-04", "AGEGROUP_YEARS05-09"]
_VALUES = {
    "LIFE_0000000029": [0.005, 0.0003, 0.0001],  # mx
    "LIFE_0000000030": [0.005, 0.001, 0.0006],  # qx
    "LIFE_0000000031": [100000.0, 99500.0, 99400.0],  # lx (decreasing)
    "LIFE_0000000032": [500.0, 100.0, 60.0],  # dx
    "LIFE_0000000033": [99540.0, 397800.0, 496800.0],  # nLx
    "LIFE_0000000034": [8000000.0, 7900000.0, 7500000.0],  # Tx
    "LIFE_0000000035": [80.0, 79.0, 75.0],  # ex
}


def _write_fixture(data_dir: Path) -> None:
    for code, values in _VALUES.items():
        records = []
        for age, value in zip(_AGES, values, strict=True):
            records.append(
                {
                    "SpatialDim": "USA",
                    "TimeDim": 2021,
                    "Dim1": "SEX_MLE",
                    "Dim2": age,
                    "NumericValue": value,
                }
            )
        (data_dir / f"{code}.json").write_text(json.dumps({"value": records}))


def test_load_lifetables_fixture(tmp_path: Path) -> None:
    _write_fixture(tmp_path)
    df = load_lifetables(tmp_path)

    assert len(df) == len(_AGES)
    assert set(df["sex"]) == {"male"}
    assert list(df["age_start"]) == [0, 1, 5]
    assert list(df["age_end"]) == [1, 5, 10]

    # Survivorship lx is monotonic non-increasing with age.
    lx = df.sort_values("age_start")["lx"].tolist()
    assert all(a >= b for a, b in zip(lx[:-1], lx[1:], strict=True))

    # Every declared indicator column is present.
    for column in INDICATOR_COLUMNS.values():
        assert column in df.columns

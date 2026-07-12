"""Tests for the MDB -> GHE cause normalization and garbage redistribution."""

from pathlib import Path

import pandas as pd

from hwid_pipeline.harmonize.normalize import normalize_causes

MAPPINGS = Path("mappings")

# GHE ids used in the assertions.
IHD = 1130  # ischaemic heart disease (Group II)
LUNG = 680  # trachea/bronchus/lung cancer (Group II)
SELF_HARM = 1610  # self-harm (Group III)


def _cell(icd_deaths: dict[str, int]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "country_code": 2450,
            "year": 2010,
            "sex": "male",
            "age_start": 60,
            "age_end": 64,
            "icd10": list(icd_deaths),
            "deaths": list(icd_deaths.values()),
        }
    )


def test_redistribution_conserves_total_and_drops_garbage() -> None:
    mdb = _cell({"I219": 100, "C349": 50, "X700": 10, "R99": 20})
    out = normalize_causes(mdb, MAPPINGS)
    assert out["deaths"].sum() == 180  # nothing lost or created (100+50+10+20)
    assert out["ghe_id"].notna().all()  # no garbage rows survive


def test_ill_defined_spreads_over_groups_one_and_two_only() -> None:
    # R99 is ill-defined: its 20 deaths go to Group I/II (IHD, lung) pro-rata,
    # never to the Group III self-harm cause.
    mdb = _cell({"I219": 100, "C349": 50, "X700": 10, "R99": 20})
    out = normalize_causes(mdb, MAPPINGS).set_index("ghe_id")["deaths"]
    assert out[SELF_HARM] == 10  # untouched
    assert out[IHD] == 100 + 20 * (100 / 150)  # 113.33...
    assert out[LUNG] == 50 + 20 * (50 / 150)  # 56.66...

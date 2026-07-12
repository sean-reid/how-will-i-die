"""Tests for the WHO Mortality Database melt logic.

These exercise the wide-to-tidy transform on a tiny inline fixture so the
age-band collapse and sex mapping are pinned without touching the network.
"""

import pandas as pd

from hwid_pipeline.ingest.mdb import AGE_BANDS, melt_deaths, read_country_rows


def _wide_row(country, year, sex, cause, deaths):
    """Build one wide MDB row. ``deaths`` maps Deaths2..Deaths25 -> count."""
    row = {
        "Country": country,
        "Year": year,
        "Sex": sex,
        "Frmat": "00",
        "List": "104",
        "Admin1": pd.NA,
        "SubDiv": pd.NA,
        "Cause": cause,
    }
    for k in range(1, 27):
        row[f"Deaths{k}"] = 0
    for col, value in deaths.items():
        row[col] = value
    return row


def test_infant_columns_collapse_into_single_0_4_band():
    # Deaths2..Deaths6 are the single-year 0,1,2,3,4 columns.
    wide = pd.DataFrame(
        [
            _wide_row(
                2450,
                2010,
                1,
                "I219",
                {"Deaths2": 1, "Deaths3": 2, "Deaths4": 3, "Deaths5": 4, "Deaths6": 5},
            )
        ]
    )
    tidy = melt_deaths(wide)

    band = tidy[(tidy["age_start"] == 0) & (tidy["age_end"] == 4)]
    assert len(band) == 1
    assert band["deaths"].iloc[0] == 1 + 2 + 3 + 4 + 5


def test_five_year_bands_map_and_95_plus_is_open_ended():
    wide = pd.DataFrame(
        [
            _wide_row(
                4080,
                2015,
                2,
                "C509",
                {"Deaths7": 10, "Deaths14": 40, "Deaths25": 7},
            )
        ]
    )
    tidy = melt_deaths(wide).set_index(["age_start", "age_end"])

    assert tidy.loc[(5, 9), "deaths"] == 10
    assert tidy.loc[(40, 44), "deaths"] == 40
    # 95+ open-ended band.
    assert tidy.loc[(95, 125), "deaths"] == 7


def test_sex_is_mapped_to_labels_and_9_is_dropped_upstream():
    wide = pd.DataFrame(
        [
            _wide_row(3160, 2000, 1, "A009", {"Deaths10": 3}),
            _wide_row(3160, 2000, 2, "A009", {"Deaths10": 4}),
        ]
    )
    tidy = melt_deaths(wide)
    labels = set(tidy["sex"].unique())
    assert labels == {"male", "female"}


def test_output_columns_and_band_count():
    wide = pd.DataFrame([_wide_row(5020, 2005, 1, "J189", {"Deaths20": 2})])
    tidy = melt_deaths(wide)

    assert list(tidy.columns) == [
        "country_code",
        "year",
        "sex",
        "age_start",
        "age_end",
        "icd10",
        "deaths",
    ]
    # 24 wide age columns collapse to 20 distinct bands (0-4 plus 5-9..95+).
    distinct_bands = {tuple(b) for b in AGE_BANDS.values()}
    assert len(distinct_bands) == 20
    assert len(tidy) == 20


def test_read_country_rows_filters(tmp_path):
    # National detailed row, an all-causes rollup, a subnational row, a
    # condensed-list row, an unspecified-sex row and a non-target country.
    header = (
        "Country,Admin1,SubDiv,Year,List,Cause,Sex,Frmat,IM_Frmat,"
        + ",".join(f"Deaths{k}" for k in range(1, 27))
        + ",IM_Deaths1,IM_Deaths2,IM_Deaths3,IM_Deaths4"
    )

    def line(country, admin1, subdiv, list_code, cause, sex):
        deaths = ["0"] * 26
        deaths[9] = "5"  # Deaths10 -> 20-24
        return (
            f"{country},{admin1},{subdiv},2010,{list_code},{cause},{sex},00,01,"
            + ",".join(deaths)
            + ",0,0,0,0"
        )

    rows = [
        header,
        line(2450, "", "", "104", "I219", 1),  # keep
        line(2450, "", "", "104", "AAA", 1),  # drop: all-causes rollup
        line(2450, "10", "", "104", "I219", 1),  # drop: subnational (Admin1 set)
        line(2450, "", "", "101", "1027", 1),  # drop: condensed list
        line(2450, "", "", "104", "I219", 9),  # drop: unspecified sex
        line(9999, "", "", "104", "I219", 1),  # drop: country not in scope
    ]
    csv_path = tmp_path / "Morticd10_test"
    csv_path.write_text("\n".join(rows) + "\n")

    kept = read_country_rows(csv_path)
    assert len(kept) == 1
    assert kept.iloc[0]["Cause"] == "I219"
    assert kept.iloc[0]["Country"] == 2450

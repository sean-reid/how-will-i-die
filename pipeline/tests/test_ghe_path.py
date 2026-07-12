"""Tests for the GHE fallback path: coarse-band to life-table-grid mapping."""

from hwid_pipeline.project.cohort import _containing_band

# Life-table band starts (also the MDB cause grid).
LIFE_TABLE_STARTS = [0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55, 60, 65, 70, 75, 80, 85]
# GHE country cause grid: seven coarse bands.
GHE_STARTS = [0, 5, 15, 30, 50, 60, 70]


def test_mdb_grid_is_identity_with_infant_fold() -> None:
    # When the cause grid equals the life-table grid, each band maps to itself
    # and the two infant bands (0 and 1) both fold to 0.
    assert _containing_band(0, LIFE_TABLE_STARTS) == 0
    assert _containing_band(1, LIFE_TABLE_STARTS) == 0
    assert _containing_band(40, LIFE_TABLE_STARTS) == 40
    assert _containing_band(85, LIFE_TABLE_STARTS) == 85


def test_ghe_grid_nests_fine_bands_in_coarse() -> None:
    # Each fine life-table band takes the cause shares of the coarse GHE band it
    # nests inside (the largest coarse start not exceeding the age).
    assert _containing_band(1, GHE_STARTS) == 0
    assert _containing_band(10, GHE_STARTS) == 5
    assert _containing_band(20, GHE_STARTS) == 15
    assert _containing_band(25, GHE_STARTS) == 15
    assert _containing_band(35, GHE_STARTS) == 30
    assert _containing_band(55, GHE_STARTS) == 50
    assert _containing_band(85, GHE_STARTS) == 70

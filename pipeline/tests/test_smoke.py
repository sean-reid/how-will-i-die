"""Smoke tests: the package imports and the common schema is well-formed."""

import hwid_pipeline


def test_version() -> None:
    assert hwid_pipeline.__version__


def test_common_schema_has_core_dimensions() -> None:
    for column in ("country", "sex", "age_start", "cause", "year", "deaths", "population"):
        assert column in hwid_pipeline.COMMON_COLUMNS

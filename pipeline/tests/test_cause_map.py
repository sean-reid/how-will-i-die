"""Spot-check ICD-10 -> GHE mappings against known WHO Annex Table A entries."""

import pytest

from hwid_pipeline.harmonize.cause_map import map_icd10, normalize


def test_normalize_strips_dots_and_case():
    assert normalize("i21.9") == "I219"
    assert normalize(" C34 ") == "C34"


@pytest.mark.parametrize(
    ("code", "ghe_id"),
    [
        ("I219", 1130),  # acute MI -> ischaemic heart disease (I20-I25)
        ("I25", 1130),
        ("C349", 680),  # lung cancer (C33-C34)
        ("C509", 700),  # breast cancer (C50)
        ("C61", 740),  # prostate cancer
        ("E119", 800),  # type 2 diabetes (E10-E14)
        ("E112", 1272),  # diabetic CKD -> more specific 4-char code wins
        ("J440", 1180),  # COPD
        ("I639", 1140),  # cerebral infarction -> stroke (I60-I69)
        ("A419", 370),  # sepsis -> other infectious diseases
        ("B24", 102),  # HIV other
        ("B200", 101),  # HIV resulting in TB -> exact 4-char code wins
        ("W19", 1550),  # fall
        ("X00", 1560),  # fire
        ("X640", 1610),  # intentional self-poisoning -> self-harm (X60-X84)
        ("X85", 1620),  # interpersonal violence
        ("Y360", 1630),  # war -> collective violence
        ("R95", 1505),  # SIDS (not garbage)
    ],
)
def test_known_mappings(code, ghe_id):
    assert map_icd10(code).ghe_id == ghe_id


def test_r99_is_ill_defined_garbage():
    m = map_icd10("R99")
    assert m.is_garbage is True
    assert m.garbage_type == "ill_defined"


def test_i50_heart_failure_is_garbage_but_still_mapped():
    m = map_icd10("I50")
    assert m.is_garbage is True
    assert m.garbage_type == "cardiovascular"
    assert m.ghe_id == 1160  # nominally "other circulatory diseases"


def test_undetermined_intent_injury_is_garbage():
    m = map_icd10("Y20")
    assert m.is_garbage is True
    assert m.garbage_type == "injury_undetermined_intent"


def test_unspecified_cancer_site_is_garbage():
    assert map_icd10("C80").garbage_type == "cancer_unspecified_site"


def test_group_fallback_used_when_no_leaf():
    # M14 has no leaf musculoskeletal category; falls back to Group II umbrella.
    m = map_icd10("M14")
    assert m.ghe_id == 600
    assert "fallback" in m.note


def test_names_and_group_populated():
    m = map_icd10("I219")
    assert m.ghe_name == "Ischaemic heart disease"
    assert m.group == "II"

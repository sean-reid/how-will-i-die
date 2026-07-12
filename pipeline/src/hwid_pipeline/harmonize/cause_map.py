"""Map detailed ICD-10 codes onto WHO GHE cause categories.

The mapping tables live in ``pipeline/mappings`` and are transcribed from the
WHO Global Health Estimates 2021 cause-of-death methods, Annex Table A. A code
is resolved to the most specific (narrowest) matching ICD-10 range; group-level
umbrella ranges are only used as a fallback when no detailed range matches.
Garbage / ill-defined codes are flagged separately so they can be redistributed
downstream.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

MAPPINGS_DIR = Path(__file__).resolve().parents[3] / "mappings"

# GHE ids that denote whole groups; their ranges are fallback-only.
GROUP_IDS = {10, 600, 1510, 1700}

_KEY_WIDTH = 7


@dataclass(frozen=True)
class CauseMatch:
    """Result of mapping an ICD-10 code."""

    code: str
    ghe_id: int | None
    ghe_name: str | None
    group: str | None
    is_garbage: bool
    garbage_type: str | None
    note: str


def normalize(code: str) -> str:
    """Uppercase an ICD-10 code and strip dots and surrounding whitespace."""
    return code.strip().upper().replace(".", "")


def _key(code: str, pad: str) -> int:
    """Encode a normalized code as a comparable base-36 integer.

    The code is right-padded to a fixed width with ``pad`` so codes of
    different lengths compare correctly. ``0`` pads a lower bound, ``Z`` pads an
    upper bound so an upper bound of ``I25`` includes ``I259``.
    """
    padded = (code + pad * _KEY_WIDTH)[:_KEY_WIDTH]
    value = 0
    for ch in padded:
        if ch.isdigit():
            digit = ord(ch) - ord("0")
        else:
            digit = ord(ch) - ord("A") + 10
        value = value * 36 + digit
    return value


@dataclass(frozen=True)
class _Range:
    start: str
    end: str
    payload: object
    note: str
    lower: int
    upper: int
    span: int


def _build_range(start: str, end: str, payload: object, note: str) -> _Range:
    return _Range(
        start=start,
        end=end,
        payload=payload,
        note=note,
        lower=_key(start, "0"),
        upper=_key(end, "Z"),
        span=_key(end, "0") - _key(start, "0"),
    )


@lru_cache(maxsize=1)
def _load_causes() -> dict[int, tuple[str, str]]:
    causes: dict[int, tuple[str, str]] = {}
    with open(MAPPINGS_DIR / "ghe_causes.csv", newline="") as f:
        for row in csv.DictReader(f):
            causes[int(row["ghe_id"])] = (row["ghe_name"], row["group"])
    return causes


@lru_cache(maxsize=1)
def _load_icd_ranges() -> tuple[list[_Range], list[_Range]]:
    detailed: list[_Range] = []
    fallback: list[_Range] = []
    with open(MAPPINGS_DIR / "icd10_to_ghe.csv", newline="") as f:
        for row in csv.DictReader(f):
            gid = int(row["ghe_id"])
            rng = _build_range(row["icd10_start"], row["icd10_end"], gid, row["note"])
            (fallback if gid in GROUP_IDS else detailed).append(rng)
    return detailed, fallback


@lru_cache(maxsize=1)
def _load_garbage() -> list[_Range]:
    ranges: list[_Range] = []
    with open(MAPPINGS_DIR / "garbage_codes.csv", newline="") as f:
        for row in csv.DictReader(f):
            rng = _build_range(
                row["icd10_start"], row["icd10_end"], row["garbage_type"], row["note"]
            )
            ranges.append(rng)
    return ranges


def _best(code_key: int, ranges: list[_Range]) -> _Range | None:
    best: _Range | None = None
    for rng in ranges:
        if rng.lower <= code_key <= rng.upper:
            if best is None or rng.span < best.span:
                best = rng
    return best


def map_icd10(code: str) -> CauseMatch:
    """Map an ICD-10 code string to a GHE cause, flagging garbage codes.

    The most specific detailed range wins; a group-level range is used only if
    no detailed range matches. Garbage status is reported independently, so a
    code can carry both a nominal GHE id and a garbage flag (e.g. I50).
    """
    norm = normalize(code)
    code_key = _key(norm, "0")

    detailed, fallback = _load_icd_ranges()
    match = _best(code_key, detailed) or _best(code_key, fallback)

    ghe_id = match.payload if match else None
    note = match.note if match else ""
    name = group = None
    if ghe_id is not None:
        name, group = _load_causes().get(ghe_id, (None, None))

    garbage = _best(code_key, _load_garbage())

    return CauseMatch(
        code=norm,
        ghe_id=ghe_id,
        ghe_name=name,
        group=group,
        is_garbage=garbage is not None,
        garbage_type=(garbage.payload if garbage else None),
        note=note,
    )

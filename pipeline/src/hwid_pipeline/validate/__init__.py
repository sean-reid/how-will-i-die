"""Checks that fail the build when the numbers are not defensible.

Invariants:
- every cohort's cause shares sum to 1 (within tolerance),
- all shares in [0, 1], survival monotone non-increasing, hazards >= 0,
- no projected rate outside the historical range by more than a set factor.

Benchmarks:
- implied life expectancy matches published figures within tolerance,
- lifetime cause shares match published lifetime-risk figures (e.g. lifetime
  risk of death from cardiovascular disease or cancer),
- hold-out back-test: fit to earlier years, compare projected vs actual shares.
"""

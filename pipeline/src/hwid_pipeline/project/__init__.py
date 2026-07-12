"""Turn observed rates into a lifetime cause-of-death distribution.

Steps:
1. Rate estimation with smoothing (Poisson with shrinkage) so sparse or zero
   cells do not produce unstable trends.
2. Coherent forward projection: fit the trend in cause shares constrained to
   sum to an independently projected all-cause trend, not independent per-cause
   log-linear fits (which diverge over a lifetime horizon). Exclude the
   COVID-distorted 2020-2021 years as trend anchors.
3. Competing-risks life table on the true cohort diagonal: a person starting at
   age a in the base year sees age a+k rates from base_year+k. Survival S(a)
   comes from WHO life tables; each cause's lifetime share is the
   S-weighted cumulative incidence, so the shares sum to exactly 1.
"""

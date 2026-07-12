# How Will I Die?

A small web app that shows the most likely eventual causes of death for people
who share your country, age, and sex, projected forward from WHO mortality data.
Pick a country, enter an age, choose a sex, and it returns a ranked list of
causes with an approximate likelihood for each.

It is a fast static site. All the heavy work (trend fitting, forward
projection, competing-risks life table) happens once at build time and is baked
into a small precomputed lookup; the page just reads and renders it.

## Not a personal prediction

This is population statistics, not a forecast about you. The rankings describe
what tends to happen across a whole demographic group. They are model
projections with real uncertainty, so the app leads with rank order and shows
approximate likelihoods rather than false-precision decimals. Nothing here is
medical or actuarial advice.

## How it works

The numbers answer: for someone alive at your age, in your country, of your sex,
what fraction will eventually die of each cause? That is computed with a
competing-risks life table run over the cohort's remaining life on
forward-projected rates.

- Survival (the life table) comes from WHO's completeness-adjusted life tables.
- The split of deaths across causes at each age comes from the WHO Mortality
  Database (registered deaths, five-year age groups), with ill-defined ("garbage")
  codes redistributed onto real causes so the ranking is not distorted.
- Rates are projected forward coherently (cause shares constrained to a single
  all-cause trend) along the true cohort diagonal, then integrated into a
  lifetime distribution whose cause shares sum to one.

v1 covers a set of countries with near-complete registration and detailed
ICD-10 coding (United States, United Kingdom, Germany, France, Japan, Canada,
Australia), which lets us prove the method on clean data before expanding.

## Layout

```
pipeline/     Python build pipeline (uv): raw WHO data -> projection -> lookup
  src/hwid_pipeline/{ingest,harmonize,project,validate}
  tests/
web/          Static site (HTML/CSS/JS) that reads the precomputed lookup
  data/       Per-country lookup shards + index.json (committed, tiny)
data/
  raw/        Downloaded WHO sources (gitignored, large)
  intermediate/  Committed normalized snapshot + provenance manifest
```

The build is two tiers so the data stays reproducible. The heavy
`raw -> normalized intermediate` step is run manually and commits a versioned
snapshot plus a manifest (source URLs, WHO file dates, checksums). The light
`intermediate -> projection -> lookup` step is deterministic and byte-stable, so
CI can rebuild it and confirm it matches what is committed.

## Develop

Pipeline (from `pipeline/`):

```
uv sync
uv run ruff check .
uv run pytest
```

Site (from `web/`), served over HTTP because it uses ES modules:

```
python3 -m http.server 8000
```

## Data and attribution

Mortality data comes from the World Health Organization:

- WHO Mortality Database: https://platform.who.int/mortality
- WHO Global Health Estimates: https://www.who.int/data/global-health-estimates

The code is licensed under the MIT License (see [LICENSE](LICENSE)). The WHO
data is not covered by that license and remains subject to WHO's own terms;
cite WHO and the data vintage when using it, and do not imply WHO endorsement.

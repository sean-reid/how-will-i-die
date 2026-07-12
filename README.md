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

- Survival (the life table) comes from WHO GHO life tables, which cover every
  country.
- The split of deaths across causes at each age comes from one of two sources,
  depending on the country (see coverage below), with ill-defined ("garbage")
  codes redistributed onto real causes so the ranking is not distorted.
- Rates are projected forward coherently: a Lee-Carter fit sets the all-cause
  mortality level, compositional-data (CoDa) forecasting sets the cause mix, and
  the two are combined on the cohort diagonal by a competing-risks life table.
  That yields lifetime cause shares that sum to one. Uncertainty is estimated
  from simulated drift and composition and then bounded.

## Coverage

About 185 countries, in two data tiers for the cause split:

- **Default:** the WHO Mortality Database (registered deaths, detailed ICD-10,
  fine five-year age groups) for the roughly 101 countries with recent detailed
  registration.
- **Fallback:** WHO Global Health Estimates 2021 country data (modeled, coarser
  age bands) for the roughly 84 countries without recent registration. These are
  badged in the UI as a regional modeled estimate with lower detail and are given
  wider uncertainty intervals.

The Mortality Database identifies countries by WHO numeric code, which is
crosswalked to ISO3 so both sources and the life tables line up.

## Layout

```
pipeline/     Python build pipeline (uv): raw WHO data -> projection -> lookup
  src/hwid_pipeline/
    ingest/     mdb.py, ghe.py, lifetable.py    raw WHO sources -> intermediate
    harmonize/  normalize.py, cause_map.py      ICD-10 -> GHE causes, garbage
    project/    lee_carter.py, composition.py, cohort.py, run.py
                PHASE4_NOTES.md                 method notes for the projection
    validate/   checks.py
    build_lookup.py   intermediate -> per-country JSON shards in web/data
    check_lookup.py   CI determinism gate: fails if rebuilt shards drift
  mappings/     Reference CSVs (see mappings/README.md)
    ghe_causes.csv, icd10_to_ghe.csv, garbage_codes.csv
    display_groups.csv      display-group rollup for the ranked list
    mdb_iso3.csv            WHO numeric country code -> ISO3 crosswalk
    cause_descriptions.csv  lay cause definitions
  tests/
web/          Static site (HTML/CSS/JS), esbuild build to web/dist
  data/       Per-country lookup shards + index.json (committed, tiny)
data/
  raw/            Downloaded WHO sources (gitignored, large)
  intermediate/   Committed normalized snapshot + provenance manifest:
                  cause_deaths.parquet, ghe_cause_deaths.parquet,
                  who_lifetables.parquet, country_names.csv, manifest.json
```

The build is two tiers so the data stays reproducible. The heavy
`raw -> normalized intermediate` step is run manually and commits a versioned
snapshot plus a manifest (source URLs, WHO file dates, checksums). The light
`intermediate -> projection -> lookup` step (`hwid_pipeline.build_lookup`) is
deterministic and byte-stable, so CI can rebuild it and confirm it matches what
is committed; `hwid_pipeline.check_lookup` is the gate that fails on any drift.

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

- WHO GHO life tables (survival, all countries):
  https://www.who.int/data/gho
- WHO Mortality Database (registered deaths, default cause split):
  https://platform.who.int/mortality
- WHO Global Health Estimates (modeled country cause split, fallback tier):
  https://www.who.int/data/global-health-estimates

The WHO numeric-to-ISO3 country crosswalk lives in
`pipeline/mappings/mdb_iso3.csv`.

The code is licensed under the MIT License (see [LICENSE](LICENSE)). The WHO
data is not covered by that license and remains subject to WHO's own terms;
cite WHO and the data vintage when using it, and do not imply WHO endorsement.

# Phase 4 design notes: running the projection on coarse GHE cause bands

Phase 4 expands the site from 7 countries to all 185 WHO member states by
swapping the cause-split source from the WHO Mortality Database (MDB, annual,
5-year ages) to WHO Global Health Estimates (GHE) country files. This note is
about the one design decision that changes: the GHE cause split is published on
coarse, uneven age bands, and the competing-risks integration in `cohort.py`
runs on the finer life-table grid. How we bridge those two grids is the key open
decision. Nothing here is implemented yet.

## What each side actually provides

- Survival side (unchanged): WHO GHO life tables via `ingest/lifetable.py`.
  Abridged 5-year grid, band starts `0, 1, 5, 10, 15, ..., 80, 85+`. Confirmed
  available for all 185 member states (see coverage note below). This side keeps
  its full resolution in Phase 4. The coarse cause bands do not affect *when* a
  cohort dies, only *which cause* it is assigned when it does.
- Cause-split side (new): `ingest/ghe.py` -> `ghe_country_deaths.parquet`.
  Deaths by GHE cause on seven age bands: `0-4, 5-14, 15-29, 30-49, 50-59,
  60-69, 70+`. (The GHE region workbook additionally splits 0-4 into 0-28 days
  and 1-59 months; the country workbook does not, so Phase 4 has seven bands,
  not eight.) Values are published in thousands; cause *shares* are
  unit-invariant, so that does not matter.

## The one property that makes this easy

Every GHE band boundary (5, 15, 30, 50, 60, 70) also lies on the life-table
5-year grid. So no life-table band ever straddles two GHE bands: each fine band
nests wholly inside exactly one coarse band.

    GHE band     life-table bands it contains
    0-4          [0,1), [1,5)
    5-14         [5,10), [10,15)
    15-29        [15,20), [20,25), [25,30)
    30-49        [30,35), [35,40), [40,45), [45,50)
    50-59        [50,55), [55,60)
    60-69        [60,65), [65,70)
    70+          [70,75), [75,80), [80,85), 85+

This means the bridge needs no splitting or apportioning of a fine band across
coarse bands. It only needs to decide the cause composition to hand each fine
band. That is a graduation choice, and the options below differ only in whether
the composition is allowed to vary *within* a GHE band.

## Options for graduating the seven bands onto the life-table grid

### Option A (recommended): piecewise-constant assignment

Every life-table band inside a GHE band uses that GHE band's cause shares,
unchanged. Cause composition is a step function of age, flat within each coarse
band. This is exactly what `cohort.py` already does for infants, generalised:
`_cause_band` currently maps life-table ages 0 and 1 both to cause band 0. For
Phase 4 it becomes a full lookup from each life-table start to its containing
GHE start:

    0,1 -> 0 ; 5,10 -> 5 ; 15,20,25 -> 15 ; 30,35,40,45 -> 30 ;
    50,55 -> 50 ; 60,65 -> 60 ; 70,75,80,85 -> 70

`composition.py` then groups by the GHE `age_start` (7 bands) instead of the
MDB `age_start` (18 bands). Nothing else in the integration changes.

Why this is the default: it invents no sub-band structure the data does not
contain, it is a one-line change to the mapping plus a different grouping key,
and it is honest. It states plainly that within a GHE band we do not know how
the cause mix shifts with finer age.

### Option B (optional cosmetic upgrade): smooth graduation of shares

Fit a monotone interpolant (for example PCHIP) to the centered-log-ratio shares
against GHE band midpoint ages, evaluate it at each life-table band midpoint,
then inverse-transform back to shares. This removes the visible step at band
boundaries and gives a gradual transition (for example the rise of cancer across
30-49). It is interpolation, not information: it fabricates the within-band
gradient from the between-band slope. If used, gate it behind a flag and label
it as interpolation, never present it as observed resolution.

### Option C (not recommended): graduate the underlying counts/rates

Graduate cause-specific counts or rates onto the fine grid (Beers, penalized
spline) before forming fractions. Heavier, and because the projection only needs
ratios it buys almost nothing over Option B while adding a lot of machinery and
new failure modes. Skip unless a later need for absolute counts appears.

Recommendation: ship Option A. Keep Option B available behind a flag for a later
visual-polish pass if the step function looks jarring in the UI.

## Combining the coarse split with the finer life tables

No change to the competing-risks math in `cohort.py`. March the cohort along the
age diagonal on the life-table grid as today; all-cause `q` per fine band still
comes from the (fine, full-resolution) life-table / Lee-Carter mortality. At each
fine band, multiply the band's death probability by the cause-share vector of
its containing GHE band (Option A) or the graduated vector (Option B). Shares
still sum to one per band, the terminal band still absorbs, so lifetime cause
shares still sum to one. The only code touched is the age-to-cause-band mapping
and the grouping key in composition fitting.

Trend fitting caveat: the GHE country files exist for 2000, 2010, 2015, 2019,
2020, 2021 only (six points, uneven spacing), versus the MDB's near-annual
series. The composition trend fit and any Lee-Carter-style cause drift must be
robust to sparse, unevenly spaced years. Center on actual calendar years, not on
an index, and expect wider trend standard errors.

## Honesty implications (flag prominently)

- Lower cause resolution for fallback countries. In a v1 (MDB) country a
  30-year-old and a 49-year-old get different cause mixes across four 5-year
  bands; in a GHE country they share one 30-49 mix. The site should mark GHE
  countries as lower-resolution (a data-quality / resolution badge or footnote),
  not silently blend them with the seven high-resolution countries.
- Modeled, not registered. This is the larger caveat. The seven v1 countries use
  registered deaths; GHE country splits are modeled estimates, and for countries
  with weak vital registration the cause mix carries substantial WHO uncertainty
  ranges. Uncertainty intervals for GHE countries should be visibly wider, and
  the methodology text should say the split is modeled.
- Survival stays full-resolution everywhere. Worth stating positively: life
  expectancy and the survival curve are on the same abridged grid for all 185
  countries, so only the cause attribution is coarser, not the timing of death.

## Coverage confirmation (both sides, 185 countries)

The GHO life-table OData API returns life tables for exactly the same 185 member
states as the GHE country deaths file. Queried
`LIFE_0000000031` (lx) filtered to 2021 / both sexes / age 0-1: 185 rows of
`SpatialDimType == COUNTRY` (plus 6 regions, 4 World Bank income groups, 1
global). The ISO-3 sets from the two sources are identical (empty symmetric
difference), so survival and cause-split join one-to-one with no gaps and no
orphans. To pull all 185 for real, extend `lifetable.py` to accept a country
list (or drop the `SpatialDim in (...)` filter and take every `COUNTRY` row)
rather than the hard-coded seven; the reader logic itself already generalises.

## Source files (WHO GHO CDN)

Base: `https://cdn.who.int/media/docs/default-source/gho-documents/global-health-estimates/`

    2000  ghe2021_deaths_bycountry_2000.xlsx
    2010  ghe2021_deaths_bycountry_age_sex_2010_new.xlsx
    2015  ghe2021_deaths_bycountry_2015.xlsx
    2019  ghe2021_deaths_bycountry_2019.xlsx
    2020  ghe2021_deaths_bycountry_2020.xlsx
    2021  ghe2021_deaths_bycountry_2021.xlsx

`ingest/ghe.py` downloads and normalizes these; only 2021 is cached and
extracted so far.

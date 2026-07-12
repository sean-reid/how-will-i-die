# ICD-10 to WHO GHE cause mapping

Reference tables that harmonize detailed ICD-10 codes (as used in the WHO
Mortality Database) into WHO Global Health Estimates (GHE) cause categories, so
causes can be named consistently and ranked.

## Sources

- WHO Global Health Estimates 2021, cause-of-death methods:
  https://cdn.who.int/media/docs/default-source/gho-documents/global-health-estimates/ghe2021_cod_methods.pdf
  "Annex Table A: GHE cause categories and ICD-10 codes" (pages 62-67) is the
  primary source for the cause hierarchy, the ICD-10 code definitions, and the
  garbage/redistribution footnotes (footnotes a, c, d, e, f, g, h).
- WHO Mortality Database cause list crosswalk (top-level cross-check):
  https://platform.who.int/mortality/about/list-of-causes-and-corresponding-icd-10-codes

GHE release: 2021 (GHE2021), years 2000-2021.
Extraction date: 2026-07-11.

The two sources agree on the top-level group definitions (Group I communicable/
maternal/perinatal/nutritional, Group II noncommunicable, Group III injuries).
The detailed hierarchy and code ranges are transcribed verbatim from Annex
Table A of the COD methods PDF.

## Files

### `ghe_causes.csv`
The GHE cause hierarchy. Columns:
- `ghe_id`   - GHE code from Annex Table A.
- `ghe_name` - cause name (numbering prefixes such as "A." / "1." are dropped;
  the hierarchy is encoded by `level`/`parent_id`).
- `level`    - 0 group, 1 sub-category (A/B/...), 2 numbered cause, 3 lettered
  sub-cause.
- `parent_id`- `ghe_id` of the parent (blank for groups).
- `group`    - I, II, III (IV for the residual "Other pandemic-related").

### `icd10_to_ghe.csv`
ICD-10 code ranges mapped to a `ghe_id`. Columns:
- `icd10_start`, `icd10_end` - inclusive range, dotless and uppercased to match
  WHO Mortality Database code formatting (e.g. `I20`, `B200` for B20.0).
- `ghe_id` - target GHE cause.
- `note`   - source caveats, e.g. `minus ...` exclusions from the annex, or the
  `group-level fallback` tag on the wide umbrella ranges.

Ranges are emitted for the most specific (leaf) GHE categories plus three
group-level umbrella ranges (`ghe_id` 10, 600, 1510). The resolver picks the
narrowest matching range; the umbrella ranges are used only when no leaf range
matches, so a code always resolves to the finest available category.

### `cause_descriptions.csv`
Plain-language definitions of the GHE cause categories, shown when a user taps a
cause name on the site to understand what it means. Columns:
- `ghe_id`          - GHE code matching `ghe_causes.csv`.
- `lay_description` - one short, plain sentence (roughly 6-16 words) describing
  the cause in everyday words.

Covers every leaf `ghe_id` that appears in `icd10_to_ghe.csv` (the causes that
can show up in results), plus the parent and group `ghe_id`s so grouping labels
also have text. The descriptions are faithful lay glosses of the standard
meaning of each GHE cause name. They add no statistics, risk figures, or advice,
and rely on no source beyond the ordinary clinical meaning of each condition.

### `garbage_codes.csv`
Ill-defined / "garbage" codes that WHO redistributes rather than counting
directly. Columns `icd10_start, icd10_end, garbage_type, note`. Types:
- `ill_defined` - R00-R94, R96-R99, J69, J96 (footnote a). R95 is excluded
  because it maps to Sudden infant death syndrome.
- `cardiovascular` - I46, I47.2, I49.0, I50, I51.4-I51.6, I51.9, I70.9
  (footnote f) and essential hypertension I10 (footnote g).
- `injury_undetermined_intent` - Y10-Y34, Y87.2 (footnote h).
- `cancer_unspecified_site` - C76, C80, C97 (footnote c) and C55 (footnote d).

Garbage status is independent of the nominal GHE mapping: a code such as I50
(heart failure) still carries a nominal `ghe_id` (1160, other circulatory) in
`icd10_to_ghe.csv` and is separately flagged here for redistribution.

### `display_groups.csv`
Curated rollup that decides how causes are grouped into the ranked list shown to
users, so a handful of readable rows appear instead of the full GHE hierarchy.
Columns:
- `root_ghe_id`  - the `ghe_id` whose subtree rolls up into one display row.
- `display_label`- the label shown for that group (e.g. `Cancer`).

Each leaf cause is attributed to the nearest listed `root_ghe_id`; anything not
covered falls through to its group-level label.

### `mdb_iso3.csv`
Crosswalk from the WHO Mortality Database's numeric country codes to ISO3, so the
Mortality Database, the Global Health Estimates, and the life tables can be
joined on a single country key. Columns:
- `mdb_code` - WHO Mortality Database numeric country code.
- `iso3`     - ISO 3166-1 alpha-3 country code.

## Codes that could not be confidently mapped (flag for review)

- **F00 (Dementia in Alzheimer disease)**: the annex Group II definition and the
  Alzheimer/dementias category (ghe 950) both begin at F01. F00 is not covered
  by any annex range and is left unmapped. It most likely belongs with
  Alzheimer disease and other dementias (950); assign manually if F00 appears.
- **G05 (Encephalitis, myelitis in diseases classified elsewhere)**: falls in
  the gap between encephalitis (ghe 180, ...G04) and the neurological umbrella
  (G06-G98). Left unmapped pending review.
- **S00-T98 (nature-of-injury codes)**: not underlying-cause codes in WHO
  mortality data (external cause V01-Y89 is used instead), so they are
  intentionally absent.
- **Z00-Z99 and most of the U block**: not causes of death; absent by design.
  Only U04, U07, U09-U10 (COVID-related) are mapped.
- The `minus` exclusions in the annex are preserved as notes rather than as
  split ranges. Where an excluded code belongs to a sibling leaf (e.g. B20.0 vs
  B20-B24) the resolver routes it correctly via most-specific-wins. Where an
  excluded code is a garbage code (e.g. J69, J96 inside J47-J98) it is caught by
  `garbage_codes.csv` downstream.

## Coverage

Across the 2500 three-character slots A00-Y99, about 81% resolve to a GHE id
(90% of those to a leaf-specific category) and 99 more are correctly flagged as
garbage. Once the code slots that are not WHO underlying-cause codes are
excluded (S/T nature-of-injury, the unused U block, and non-existent code
slots), coverage of the valid underlying-cause ICD-10 space is effectively
complete apart from the individually flagged codes above.

## Regenerating

The tables are transcribed from Annex Table A; they are plain committed CSVs and
can be edited by hand. The loader/resolver lives in
`../src/hwid_pipeline/harmonize/cause_map.py` with tests in
`../tests/test_cause_map.py`.

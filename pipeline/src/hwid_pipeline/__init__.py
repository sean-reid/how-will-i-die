"""Pipeline that turns WHO mortality data into a precomputed projection lookup.

The build runs in two tiers so it stays reproducible:

1. Heavy tier (run manually): download raw WHO sources, normalize them into one
   common schema, and write a versioned intermediate snapshot plus a manifest
   recording source URLs, file dates, and checksums.
2. Light tier (run in CI): read the committed intermediate, fit trends, project
   forward, run the competing-risks life table, validate, and emit the sharded
   lookup the static site consumes.

Stage packages:
    ingest     - one module per source; each emits the common schema.
    harmonize  - cause mapping, garbage-code redistribution, age/geography.
    project    - trend fit, forward projection, competing-risks life table.
    validate   - invariants and benchmark back-tests; the build fails on these.
"""

__version__ = "0.1.0"

# The common schema every source normalizes into (tidy long form).
COMMON_COLUMNS = (
    "country",  # ISO3 code
    "source",  # "mdb" or "ghe"
    "sex",  # "male" | "female"
    "age_start",  # integer age at the start of the band
    "age_end",  # integer age at the end of the band (inclusive)
    "cause",  # harmonized GHE cause id
    "year",
    "deaths",
    "population",
)

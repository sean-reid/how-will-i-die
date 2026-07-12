"""Source readers. Each reader emits rows in the common schema.

- mdb: WHO Mortality Database (registered deaths, ICD-coded, 5-year ages).
  v1 uses this for the cause split, restricted to high-registration,
  ICD-10-detailed country-years.
- ghe: WHO Global Health Estimates (modeled, redistributed, 8 coarse bands).
  Used later as the comparable global backbone.

Survival (the life table itself) does not come from these death counts; it
comes from WHO's completeness-adjusted life tables, kept in its own reader.
"""

"""Reconcile sources onto one comparable footing.

- cause mapping: ICD-10 -> GHE cause id, from a committed, human-reviewed CSV.
- garbage-code redistribution: reassign ill-defined / unspecified codes onto
  real causes so raw MDB counts can be ranked (WHO/GBD do this; raw MDB does
  not). Without it, ill-defined codes crowd the top of the ranking.
- age and geography: keep MDB's fine bands; map countries to ISO3.
"""

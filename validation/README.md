# Validation Evidence

This folder contains the evidence required before a dataset can become an
Engineering Layer or Gold input. A successful SQL join is not validation.

Required evidence sequence:

1. `wheel_identity_validation.md` — identity, cardinality and coverage.
2. `temporal_integrity.md` — provision/removal/effective-date evidence and
   assignment ambiguity.
3. `business_rules.md` — measurement, turning, replacement and maintenance
   rules approved with engineering stakeholders.
4. `join_coverage.md` — point-in-time coverage of every downstream join.

The source queries live in `sql/validation/`. Every report must state source
snapshot, run time, query, denominator, exclusions and unresolved ambiguity.

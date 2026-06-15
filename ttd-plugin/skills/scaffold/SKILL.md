---
name: scaffold
description: Generate functional (schema) test stubs - not_null / unique - for any dbt model that currently has no tests. Pre-build, no warehouse needed.
argument-hint: ""
---

# /ttd:scaffold

Generate functional test stubs so untested models can pass the coverage gate.

Steps:
1. From the dbt project root, run: `python ttd.py scaffold`
2. Report which `_ttd_stub__*.yml` files were created and how many columns each covers
   (`_id`/`_key` columns get `not_null, unique`; the rest get `not_null`).

These stubs are a starting point - review them and fold into the real `_*__models.yml`.

## Conventions
- Run from the dbt project root; profile `dbt01`.

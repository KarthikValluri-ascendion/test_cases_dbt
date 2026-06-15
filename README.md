# TTD — Medallion dbt project with Test-Then-Deploy enforcement

A dbt Core + Snowflake project that demonstrates a **medallion architecture**
(bronze → silver → gold) wired to an automation hook that **enforces tests on
every model** and **scaffolds test stubs on the fly**.

## Architecture

| Layer | Schema | Materialization | Purpose |
|-------|--------|-----------------|---------|
| Bronze | `TTD_BRONZE` | view | Raw 1:1 passthrough of TPC-H sources (rename only) |
| Silver | `TTD_SILVER` | view | Cleaned, conformed, joined; explicit revenue math |
| Gold | `TTD_GOLD` | table | `dim_customers`, `fct_orders` (business-facing) |

Source: `SNOWFLAKE_SAMPLE_DATA.TPCH_SF1` (read-only share). Volume is bounded by
`vars: start_date` so it builds in seconds on an XS warehouse.

> Schemas are prefixed `TTD_` so they never collide with the existing
> BRONZE/SILVER/GOLD schemas in `DB01`.

## The TTD automation hook

"Enforce + scaffold", two halves:

1. **Enforce** — `macros/ttd_enforce_coverage.sql`, wired to dbt's
   `on-run-start`. It walks the parsed graph and **aborts the run** if any
   in-scope model has no test (schema, singular, or unit). No untested model
   can build.
2. **Scaffold** — `ttd/scaffold_tests.py`. Reads `target/manifest.json`, finds
   untested models, and writes `_ttd_stub__<model>.yml` with heuristic
   not_null/unique tests + a unit-test skeleton. (dbt run-hooks run SQL in the
   warehouse and can't write files, so this half is Python.)

`ttd.py` chains them:

```bash
python ttd.py scaffold   # dbt parse -> generate stubs for untested models
python ttd.py build      # scaffold -> dbt build (gate runs, then models + tests)
python ttd.py test       # dbt test only
```

## Tests

- **Functional / data-quality**: schema tests (`not_null`, `unique`,
  `relationships`, `accepted_values`, `dbt_utils.accepted_range`,
  `unique_combination_of_columns`) in the `_*__models.yml` files, plus a
  singular test in `tests/`.
- **Unit tests** (native dbt): mock inputs → assert transformation logic, in
  the `unit_tests:` blocks — covering the status-label mapping, the
  date filter, the discount/tax revenue math, and the fact roll-up + coalesce.

## Setup

```bash
dbt deps          # install dbt_utils
python ttd.py build
```

Uses the `dbt01` profile (`~/.dbt/profiles.yml`, account QUMTAAX-IO32337, DB01).

## Try the gate

Delete the tests for one model (or add a new untested model) and run
`python ttd.py build` — the run aborts before building, listing the offender.
Then `python ttd.py scaffold` generates a stub to fix it.

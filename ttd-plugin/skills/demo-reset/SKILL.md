---
name: demo-reset
description: Delete generated stubs + unit tests so the demo fixture model is untested again - the RED starting state for the Red->Green demo.
argument-hint: ""
---

# /ttd:demo-reset

Return the project to the demo's RED starting state.

Steps:
1. From the dbt project root, run: `python ttd.py demo-reset`
2. Confirm which generated files were removed and that the demo fixture
   (`fct_high_value_orders`) is now untested - the next `dbt run` / `dbt build` will fail the
   coverage gate, which is the start of the demo.

## Conventions
- Run from the dbt project root; profile `dbt01`.

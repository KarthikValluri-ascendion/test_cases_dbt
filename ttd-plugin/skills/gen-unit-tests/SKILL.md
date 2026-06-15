---
name: gen-unit-tests
description: Generate runnable characterization unit tests (real sampled given -> captured expect) for models that lack one. Samples real rows and executes the model's compiled SQL. Needs warehouse access.
argument-hint: "[<model_name> ...]"
---

# /ttd:gen-unit-tests

Generate runnable unit tests by sampling real upstream rows and capturing the model's
actual output as the expected result.

Steps:
1. From the dbt project root, run: `python ttd.py gen-unit-tests $ARGUMENTS`
   (no args = every model lacking a unit test; or pass specific model names.)
2. Report the `_ttd_unit__*.yml` files created and the given/expect row counts.

IMPORTANT - these are **characterization** tests: they pin the model's CURRENT behaviour to
catch unintended drift, NOT correctness against a spec. Always review the captured `expect`
values before trusting them. Multi-table join models may fall back to a skeleton.

## Conventions
- Run from the dbt project root; profile `dbt01`. A model's upstreams must already be built
  in the warehouse (run `/ttd:build` first).

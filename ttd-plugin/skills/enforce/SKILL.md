---
name: enforce
description: Run the Test-Then-Deploy coverage gate against the current dbt project and report any models that have no tests (schema, singular, or unit). Read-only - compiles, does not build.
argument-hint: "[--select <dbt-selector>]"
---

# /ttd:enforce

Run the TTD coverage gate. The gate is the `on-run-start` macro `ttd_enforce_coverage`,
which aborts a run if any in-scope model has no test.

Steps:
1. From the dbt project root, run: `dbt compile $ARGUMENTS`
   (`compile` fires `on-run-start`, so the gate evaluates without materialising anything.)
2. If the gate fails, surface the `TTD COVERAGE GATE FAILED` banner verbatim and list the
   uncovered model(s). If it passes, report "coverage gate passed - all in-scope models have tests."

## Conventions (all /ttd commands)
- Run from the dbt project root (the folder with `dbt_project.yml` + `ttd.py`); profile `dbt01`.
- Bypass for one run with `--vars 'ttd_enforce: false'`.

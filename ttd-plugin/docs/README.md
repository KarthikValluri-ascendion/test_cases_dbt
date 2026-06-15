# ttd — Test-Then-Deploy plugin

A Claude Code plugin that brings the Test-Then-Deploy hook to dbt + Snowflake medallion
projects: a coverage gate that **blocks untested models**, plus **auto-generated** functional
test stubs and runnable **characterization unit tests**.

## Install

```text
/plugin marketplace add KarthikValluri-ascendion/test_cases_dbt
/plugin install ttd@claude-enterprise-standards
```

Or enable per-project in `.claude/settings.json`:
```json
{ "enabledPlugins": { "ttd@claude-enterprise-standards": true } }
```

## Commands

| Command | What it does |
|---|---|
| `/ttd:enforce` | Run the coverage gate; report models with no tests (read-only compile). |
| `/ttd:scaffold` | Generate functional (schema) test stubs for untested models (pre-build). |
| `/ttd:gen-unit-tests [model ...]` | Generate runnable characterization unit tests (post-build). |
| `/ttd:build` | Full cycle: scaffold → `dbt build` (gated) → generate unit tests → run them. |
| `/ttd:demo-reset` | Remove generated tests so the demo fixture is untested again (RED state). |

All commands run against the **current dbt project** (the folder with `dbt_project.yml` +
`ttd.py`) using profile `dbt01`.

## How it works

1. **Enforce** — `assets/macros/ttd_enforce_coverage.sql` wired to `on-run-start` walks the dbt
   graph and aborts the run if any model has no test.
2. **Scaffold (functional)** — `assets/scripts/scaffold_tests.py` reads `manifest.json` and writes
   `_ttd_stub__*.yml` with `not_null`/`unique`.
3. **Generate (unit)** — `assets/scripts/generate_unit_tests.py` samples real rows, runs the
   model's compiled SQL on them, and records the output as a runnable unit test (`_ttd_unit__*.yml`).

`assets/scripts/ttd.py` orchestrates these; the plugin's skills wrap it.

## Honest caveat

Generated unit tests are **characterization tests** — they pin current behaviour to catch drift,
not correctness against a spec. Review the captured `expect` values before trusting them. See
`assets/CLAUDE.global.md` for the full enterprise standard.

## Scope

This release ships the **core command wrappers**. A `/ttd:init` installer (wire the hook into a
bare dbt project), governance hooks, and a test-quality grader are planned for a later release —
today the target project must already contain the `ttd.py` tooling (the `assets/` here is the
canonical copy).

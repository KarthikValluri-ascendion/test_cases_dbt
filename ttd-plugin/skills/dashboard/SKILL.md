---
name: dashboard
description: Build the self-contained TTD executive dashboard (HTML) + artifacts library - business KPIs from the gold layer, the test-coverage scorecard, medallion lineage, tokenomics, and the TTD workflow. Opens offline in any browser.
argument-hint: "[--product <name>] [--labor-rate <n>]"
---

# /ttd:dashboard

Generate the executive dashboard and its supporting artifacts.

Steps:
1. From the dbt project root, run: `python ttd.py dashboard $ARGUMENTS`
2. Report the console summary it prints:
   - coverage line (`N/M models tested · K tests · gate PASS/FAIL`)
   - gold KPIs line (orders · net revenue · customers · high-value)
   - tokenomics line (model · tokens in/out · estimated $ cost)
3. Point the user at the output: `artifacts/TTD_Exec_Dashboard.html` (open in any
   browser, fully offline) and the rest of the `artifacts/` library.

What it produces (in `artifacts/`):
- `TTD_Exec_Dashboard.html` - 5 tabs: Executive Summary / Test Coverage / Lineage /
  Tokenomics / Workflow. Self-contained (inline CSS + SVG, no CDN).
- `coverage_report.md` / `.csv`, `model_inventory.csv` - per-model test coverage.
- `gold_orders_by_region.csv`, `gold_orders_by_month.csv`, `high_value_orders.csv` - gold extracts.
- `run_telemetry.json` - machine-readable coverage + KPIs + tokenomics.
- `ttd_telemetry.json` - **editable** tokenomics input (model, per-step token estimates,
  wall-clock). Token figures are estimates; edit with actuals to refresh the Tokenomics tab.

## Conventions
- Run from the dbt project root; profile `dbt01`.
- Needs the gold tables already built (`python ttd.py build`) - the business KPIs are
  queried live from `DB01.TTD_GOLD`. Coverage + lineage come from the dbt manifest.

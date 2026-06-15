---
name: build
description: Full Test-Then-Deploy cycle - scaffold functional stubs, run dbt build behind the coverage gate, generate characterization unit tests for new models, then run the unit tests.
argument-hint: "[<dbt build args>]"
---

# /ttd:build

Run the complete TTD cycle in one shot.

Steps:
1. From the dbt project root, run: `python ttd.py build $ARGUMENTS`
2. Narrate the four phases as they appear in the output:
   a. functional stub(s) created (pre-build, to satisfy the gate)
   b. `TTD: coverage gate passed` then `dbt build` green
   c. characterization unit test(s) generated (post-build, sampled from the warehouse)
   d. unit tests run
3. Report the final `Done. PASS=N WARN=0 ERROR=0` line.

## Conventions
- Run from the dbt project root; profile `dbt01`.

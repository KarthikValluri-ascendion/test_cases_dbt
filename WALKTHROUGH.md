# TTD Walkthrough — annotated demo + how the hook works

Two parts:
- **Part A** — every demo step with the exact command (input), the real output, and
  commentary on what just happened.
- **Part B** — how the hook works, explained twice: once for a client (conceptual),
  once for an engineer (code-level), with the honest limitations.

All output below was captured from real runs against Snowflake (account `EX09645`,
`DB01`, profile `dbt01`).

---

# Part A — Annotated walkthrough

The story: a developer adds a new gold model, `fct_high_value_orders`, and forgets
the tests. The pipeline refuses to ship it. One command runs the hook, which
generates **both** a functional test stub and a runnable unit test, then lets the
build through.

## Step 0 — Reset to the starting line

**Input**
```
python ttd.py demo-reset
```
**Output**
```
  - removed models\gold\_ttd_stub__fct_high_value_orders.yml
  - removed models\gold\_ttd_unit__fct_high_value_orders.yml

Demo reset complete.
  2 generated file(s) removed.
  'fct_high_value_orders' is now UNTESTED.
  Next `dbt run` / `dbt build` will FAIL the TTD coverage gate (this is the demo).
  Run `python ttd.py build` to scaffold tests and go GREEN.
```
**Commentary.** `demo-reset` deletes the hook's previously generated artifacts
(the `_ttd_stub__*` functional tests and `_ttd_unit__*` unit tests). The fixture
model file stays; only its tests are gone — so it is now an untested model. This
is purely file-based, so the demo loops cleanly with no Snowflake cleanup.

## Step 1 — RED: the build refuses untested code

**Input**
```
dbt run
```
**Output (tail)**
```
Encountered an error:
Compilation Error in operation ttd-on-run-start-0 (.\dbt_project.yml)

  TTD COVERAGE GATE FAILED
  ------------------------
  The following 1 model(s) have NO tests (schema, singular, or unit):

    - fct_high_value_orders

  Every model must ship with at least one test before it can build.
  Generate stubs with:  python ttd.py scaffold
  Or exempt a prefix in dbt_project.yml (vars: ttd_exempt_prefixes).
  Or bypass for one run:  dbt build --vars 'ttd_enforce: false'
```
Exit code: `2`.

**Commentary.** The run stops at `on-run-start`, **before any model is built**.
The gate found exactly one model with no tests and aborted. `dbt build` fails
identically. This is policy enforced by the engine, not a linter you can skip.

## Step 2 — GREEN: the hook heals it

**Input**
```
python ttd.py build
```
**Output (key lines, in order)**
```
  + stub created: fct_high_value_orders (6 columns)        # 1. functional stub, PRE-build
  TTD: coverage gate passed - all in-scope models have tests.
  Done. PASS=55 WARN=0 ERROR=0 SKIP=0 NO-OP=0 TOTAL=55     # 2. build + all data tests
  + unit test created: fct_high_value_orders (1 input(s), 6 expect row(s))   # 3. unit test, POST-build
  1 of 4 START unit_test fct_high_value_orders::ut_fct_high_value_orders_characterization
  Done. PASS=5 WARN=0 ERROR=0 SKIP=0 NO-OP=0 TOTAL=5       # 4. unit tests run + pass
```
**Commentary — the four things that just happened, in order:**
1. **Scaffold (pre-build):** a functional test stub is written so the gate can
   pass. Fast, no warehouse needed.
2. **Build:** the gate passes, all models build, all 33 data tests run → green.
3. **Generate unit test (post-build):** now that the warehouse has real data, the
   hook samples real rows, runs the model's actual logic on them, and writes a
   runnable unit test pinned to that output.
4. **Run unit tests:** the new unit test executes alongside the existing ones and
   passes.

## Step 3 — The reveal (what the hook wrote)

**Input**
```
type models\gold\_ttd_stub__fct_high_value_orders.yml
```
**Output** — the functional (schema) tests:
```yaml
models:
  - name: fct_high_value_orders
    columns:
      - name: order_id
        data_tests: [not_null, unique]      # _id column -> uniqueness check
      - name: customer
        data_tests: [not_null]
      - name: region
        data_tests: [not_null]
      - name: order_date
        data_tests: [not_null]
      - name: revenue
        data_tests: [not_null]
      - name: revenue_with_tax
        data_tests: [not_null]
```

**Input**
```
type models\gold\_ttd_unit__fct_high_value_orders.yml
```
**Output (abridged)** — the runnable unit test, real `given` → real `expect`:
```yaml
unit_tests:
  - name: ut_fct_high_value_orders_characterization
    model: fct_high_value_orders
    given:
      - input: ref('fct_orders')
        rows:
          - {order_id..., net_revenue: 227739.23, ...}   # 8 real sampled rows
          - {..., net_revenue: 4345.5, ...}              # this one is < 50000
          - ... (6 more)
    expect:
      rows:
        - {order_id: 2205862, region: 'EUROPE', revenue: 227739.23, ...}
        - ... (6 rows total)                              # the 2 sub-50k rows are gone
```
**Commentary.** 8 rows went in; 6 came out. The two rows with `net_revenue` below
the model's `>= 50000` threshold were dropped — the hook captured the model's real
filtering behaviour automatically. This is a **characterization test**: it locks in
what the model does *today*.

## Step 4 — Prove the unit test has teeth

Tighten the model's filter (a realistic "logic drift"):
```sql
-- where net_revenue >= 50000      (original)
   where net_revenue >= 100000     (changed)
```
**Input**
```
dbt test --select "fct_high_value_orders,test_type:unit"
```
**Output**
```
1 of 1 FAIL 1 fct_high_value_orders::ut_fct_high_value_orders_characterization
Failure in unit_test ut_fct_high_value_orders_characterization
  actual differs from expected:
Done. PASS=1 WARN=0 ERROR=1 SKIP=0 NO-OP=0 TOTAL=2
```
**Commentary.** Changing the threshold dropped a row that the recorded `expect`
still contains, so the unit test **fails**. The generated test is not a rubber
stamp — it genuinely catches behavioural change. (Revert the model and
`python ttd.py demo-reset` to return to the start.)

## Cheat sheet

| Beat | Command |
|------|---------|
| Reset to RED | `python ttd.py demo-reset` |
| Act 1 (fails) | `dbt run` |
| Act 2 (heals + passes) | `python ttd.py build` |
| Reveal | `type models\gold\_ttd_stub__fct_high_value_orders.yml` / `_ttd_unit__...` |
| Teeth (optional) | edit the `where` threshold → `dbt test --select fct_high_value_orders,test_type:unit` |

---

# Part B — How the hook works

## B.1 For the client (conceptual)

**The gate is a reflex.** Every time the pipeline runs, the very first thing it
does is check that every model carries at least one test. If one doesn't, the run
**stops before touching the warehouse**. Untested logic physically cannot deploy.

**Two kinds of test, two kinds of protection** — the hook generates both:

| Test type | Question it answers | Example here |
|-----------|--------------------|--------------|
| **Functional** (schema) | "Is the *data* shaped correctly?" | order_id is unique and never null; revenue is never null |
| **Unit** | "Does the *logic* compute the right answer?" | given these orders, the model keeps the high-value ones and drops the rest |

**Auto-compliance.** A developer doesn't have to stop and hand-write tests to get
past the gate. The hook generates a sensible starting set automatically, so the
*easy* path is also the *compliant* path. The team then reviews and tightens what
was generated.

## B.2 For the engineer (code-level)

Three pieces. The **enforce** half is a dbt macro; the two **generate** halves are
Python that reads dbt's `manifest.json`.

### 1. Enforce — `macros/ttd_enforce_coverage.sql` (wired to `on-run-start`)
- Runs at the start of every `dbt run`/`build`/`test`.
- Iterates `graph.nodes`; for every `test` and `unit_test` node, collects the model
  `unique_id`s it depends on → the **covered** set.
- Any `model` node not in that set (and not matching `vars: ttd_exempt_prefixes`) is
  **uncovered**.
- If the uncovered list is non-empty → `exceptions.raise_compiler_error(...)`, which
  aborts the run. That is the red banner in Step 1.

### 2. Generate functional tests — `ttd/scaffold_tests.py` (PRE-build)
- Reads `target/manifest.json`; `covered_model_ids()` finds models a test/unit_test
  already depends on; everything else is a target.
- `columns_for()` takes documented columns from the manifest, else extracts them
  from the model SQL's `... as <alias>` clauses (regex, `scaffold_tests.py:25`).
- `build_stub()` writes `_ttd_stub__<model>.yml`: `not_null, unique` for columns
  ending in `_key`/`_id`, `not_null` for the rest.
- Pure file generation, no warehouse — so it can run before the build and satisfy
  the gate immediately.

### 3. Generate unit tests — `ttd/generate_unit_tests.py` (POST-build, "characterization")
A unit test needs `expect`, and you can't get `expect` from SQL text — you have to
execute it. So for each model lacking a unit test:
1. From `manifest.json`: the model's `compiled_code`, its upstream `depends_on`
   nodes, and each upstream's `relation_name`.
2. **Sample** real rows from each upstream: `dbt show --inline "select * from
   <relation>" --output json` → becomes the `given` block.
3. **Capture expected**: substitute each `relation_name` in `compiled_code` with a
   CTE of the sampled rows (typed via `information_schema` — see the `NUMBER(p,s)`
   note below), run it with `dbt show --inline ... --output json` → becomes the
   `expect` block.
4. Write `_ttd_unit__<model>.yml` with that `given`/`expect`. The result is a real,
   runnable, passing dbt unit test.

`ttd.py build` orchestrates: `scaffold` → `dbt build` → generate unit tests for the
models that were just scaffolded → `dbt test --select test_type:unit`.

### Limitations (be upfront about these)
- **Characterization tests pin *current* behaviour.** They catch *unintended
  change*, not correctness against a spec. If the model is currently wrong, the
  generated test enshrines the wrong answer — so **review generated `expect`
  values** before trusting them. They are a safety net, not a substitute for
  intent-driven tests.
- **Multi-input join models may fall back.** Independently sampled rows from two
  upstreams often don't share join keys, so the capture returns nothing. The
  generator then leaves a commented skeleton and logs why; the functional stub
  still satisfies the gate, so the build is never blocked. (The project's existing
  multi-join models ship with hand-written unit tests, so coverage isn't lost.)
- **Type precision matters.** `information_schema` reports `NUMBER` without scale, so
  a naive `cast(x as NUMBER)` truncates decimals. The generator rebuilds
  `NUMBER(precision, scale)` from `numeric_precision`/`numeric_scale` so monetary
  values (e.g. `NUMBER(38,2)`) round-trip exactly.
- **Generation needs the warehouse.** It samples and executes, so it runs *after*
  the build, using dbt's own connection via `dbt show --inline` (no extra creds).

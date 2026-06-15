# Client Demo — Test-Then-Deploy enforcement (Red → Green)

A 3-act, terminal-only demo. The story: a developer adds a new gold model and
forgets the tests. The pipeline **refuses to ship it**. One command runs the
hook, which **auto-generates the tests** and lets the build through.

Total time: ~5 minutes. Fully repeatable — reset and run again with one command.

---

## Pre-flight (once, before the client is watching)

```powershell
cd "C:\Users\karthik.valluri\OneDrive - ascendion\Desktop\dbt_demos\ttd"
dbt deps          # installs dbt_utils (skip if already done)
dbt debug         # expect: "All checks passed!"
```

Keep your terminal font large. That's the only visual; the red error and the
green `PASS=` line carry the demo.

---

## Reset to the starting line (before EVERY run, including rehearsals)

```powershell
python ttd.py demo-reset
```

> *"A developer just added a new gold model — `fct_high_value_orders`, for sales
> prioritisation — and forgot to write any tests."*

(Optional) show that the model exists and has no test file beside it:

```powershell
type models\gold\fct_high_value_orders.sql
```

---

## Act 1 — RED: the build refuses untested code

```powershell
dbt run
```

**What happens:** the run aborts immediately at the `on-run-start` gate with:

```
TTD COVERAGE GATE FAILED
------------------------
The following 1 model(s) have NO tests (schema, singular, or unit):

  - fct_high_value_orders
...
```

No models build. Exit code is non-zero.

> *"Our pipeline literally cannot deploy a model with no tests. `dbt build` fails
> the same way. This isn't a linter you can wave past — the run stops here."*

---

## Act 2 — the hook heals it (the reveal)

```powershell
python ttd.py build
```

**What happens, in order:** the hook (1) scaffolds a **functional test stub** for
`fct_high_value_orders` so the gate passes → (2) all models build, all data tests
run (`PASS=55`) → (3) generates a **runnable unit test** by sampling real rows and
capturing the model's actual output → (4) runs the unit tests (`PASS=5`).

(Optional reveal) show BOTH tests the hook wrote:

```powershell
type models\gold\_ttd_stub__fct_high_value_orders.yml   # functional: not_null / unique
type models\gold\_ttd_unit__fct_high_value_orders.yml   # unit: real given -> real expect
```

> *"One command. The hook generated both a functional test — not-null + uniqueness
> on the order key — AND a runnable unit test that captured the model's real
> filtering behaviour, then let the build through. Untested code can't reach the
> warehouse; compliant code flows automatically."*

For a full annotated walkthrough (every command + real output) and how the hook
works, see **WALKTHROUGH.md**.

(Optional Act — "tests have teeth") Tighten the model filter
(`net_revenue >= 50000` → `>= 100000`) and run
`dbt test --select "fct_high_value_orders,test_type:unit"` → the generated unit
test **FAILS**, proving it's not a rubber stamp. Revert, then `demo-reset`.

---

## Act 3 — GREEN confirmed

Point at the `PASS=N WARN=0 ERROR=0` line. Done.

To run it again (rehearsal or a second audience):

```powershell
python ttd.py demo-reset
```

…and repeat from Act 1. The reset is purely file-based, so it loops cleanly with
no Snowflake cleanup.

---

## Cheat sheet (the only 3 commands on screen)

| Beat | Command |
|------|---------|
| Reset to RED | `python ttd.py demo-reset` |
| Act 1 (fails) | `dbt run` |
| Act 2 (heals + passes) | `python ttd.py build` |

You can also double-click / run `.\demo\reset.ps1` instead of the reset command.

---

## If something goes sideways live

- **Act 1 unexpectedly passes (green):** a stub was left behind. Run
  `python ttd.py demo-reset` and retry.
- **`dbt: command not found`:** activate the right Python env, or use the full
  path to dbt.
- **Connection error:** `dbt debug` to confirm the `dbt01` profile reaches
  Snowflake before presenting.
- **Want to show it's not faked:** run `dbt build --vars 'ttd_enforce: false'`
  to prove the model builds fine *without* the gate — the gate is the only thing
  blocking it, by policy.

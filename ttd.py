#!/usr/bin/env python
"""TTD entrypoint -- the single 'automation hook' for Test-Then-Deploy.

Commands:
  python ttd.py scaffold        dbt parse -> generate functional test stubs for untested models
  python ttd.py enforce         dbt compile (the on-run-start gate reports uncovered models)
  python ttd.py gen-unit-tests  generate runnable characterization unit tests (args: model names)
  python ttd.py build           scaffold -> dbt build -> gen unit tests for new models -> run them
  python ttd.py test            dbt test only
  python ttd.py demo-reset      delete generated stubs + unit tests -> back to the demo's RED start

Why a wrapper instead of a pure dbt run-hook?
  dbt's on-run-start/on-run-end hooks execute SQL in the warehouse -- they
  cannot write test files to disk. So the ENFORCE half lives in dbt
  (macros/ttd_enforce_coverage.sql, wired to on-run-start) and the SCAFFOLD
  half is Python. This wrapper runs them in the right order.

  Two kinds of tests are generated:
    - functional (schema) stubs: not_null/unique, written PRE-build to pass the
      gate (scaffold_tests.py).
    - characterization unit tests: real given/expect, written POST-build because
      they sample + execute against the live warehouse (generate_unit_tests.py).
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SCAFFOLDER = ROOT / "ttd" / "scaffold_tests.py"
UNIT_GEN = ROOT / "ttd" / "generate_unit_tests.py"


def run(cmd: list[str]) -> int:
    print(f"\n$ {' '.join(cmd)}")
    return subprocess.run(cmd, cwd=ROOT).returncode


def dbt(*args: str) -> int:
    return run(["dbt", *args])


def scaffold() -> int:
    # Parse first so the manifest reflects the current models, then scaffold.
    rc = dbt("parse")
    if rc:
        return rc
    return run([sys.executable, str(SCAFFOLDER)])


def stubbed_models() -> list[str]:
    """Model names that currently have a functional stub (i.e. were freshly
    scaffolded because they had no tests) -- the targets for unit-test gen."""
    return [
        p.name[len("_ttd_stub__"):-len(".yml")]
        for p in (ROOT / "models").rglob("_ttd_stub__*.yml")
    ]


def gen_unit_tests(models: list[str], compile_first: bool = True) -> int:
    """Generate characterization unit tests. Needs compiled_code in the
    manifest, so compile first unless the caller just built."""
    if compile_first:
        rc = dbt("compile", "--vars", "ttd_enforce: false")
        if rc:
            return rc
    return run([sys.executable, str(UNIT_GEN), *models])


def demo_reset() -> int:
    """Delete every generated test stub + unit test, returning the project to
    the demo's RED starting state (the untested fixture fails the gate again)."""
    stubs = sorted((ROOT / "models").rglob("_ttd_stub__*.yml")) + \
        sorted((ROOT / "models").rglob("_ttd_unit__*.yml"))
    for stub in stubs:
        stub.unlink()
        print(f"  - removed {stub.relative_to(ROOT)}")
    print("\nDemo reset complete.")
    print(f"  {len(stubs)} generated file(s) removed.")
    print("  'fct_high_value_orders' is now UNTESTED.")
    print("  Next `dbt run` / `dbt build` will FAIL the TTD coverage gate (this is the demo).")
    print("  Run `python ttd.py build` to scaffold tests and go GREEN.")
    return 0


def main(argv: list[str]) -> int:
    cmd = argv[1] if len(argv) > 1 else "build"
    passthrough = argv[2:]

    if cmd == "scaffold":
        return scaffold()
    if cmd == "enforce":
        # `dbt parse` runs on-run-start? No -- parse skips hooks. Use compile,
        # which triggers on-run-start and therefore the coverage gate.
        return dbt("compile", *passthrough)
    if cmd == "gen-unit-tests":
        return gen_unit_tests(passthrough)
    if cmd == "build":
        rc = scaffold()
        if rc:
            return rc
        # on-run-start gate fires here; build aborts if anything is still uncovered.
        rc = dbt("build", *passthrough)
        if rc:
            return rc
        # Post-build enrichment: any model that just needed a functional stub is
        # a brand-new model -- generate a runnable characterization unit test for
        # it (the warehouse + compiled_code now exist), then run the unit tests.
        new_models = stubbed_models()
        if new_models:
            rc = gen_unit_tests(new_models, compile_first=False)
            if rc:
                return rc
            return dbt("test", "--select", "test_type:unit")
        return 0
    if cmd == "test":
        return dbt("test", *passthrough)
    if cmd == "demo-reset":
        return demo_reset()

    print(__doc__)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

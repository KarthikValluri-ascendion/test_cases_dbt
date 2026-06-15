"""TTD unit-test generator -- runnable *characterization* unit tests, on the fly.

A dbt unit test is `given` (mock input rows per upstream) + `expect` (output rows).
`expect` cannot be derived from SQL text alone -- it has to be executed. So for
every model that has no unit test, this generator:

  1. samples a few REAL rows from each upstream relation,
  2. runs the model's ACTUAL compiled SQL on exactly those rows (by substituting
     each upstream relation with a CTE of the sampled rows), capturing the output,
  3. writes a runnable `unit_tests:` block with given = the samples and
     expect = the captured output, into `_ttd_unit__<model>.yml`.

The result is a *characterization (golden) test*: it pins the model's CURRENT
behaviour, so any later change that alters the output fails the test. It catches
unintended drift -- not correctness against a spec. Honest about that.

Execution uses dbt's own warehouse connection via `dbt show --inline`, so no
separate credentials are needed. Anything that can't be handled safely (e.g. a
multi-input join whose independent samples don't share keys, returning no rows)
falls back to leaving the model's commented unit-test skeleton in place, with a
logged reason. The functional stub still satisfies the coverage gate, so a build
is never blocked by a fallback.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
MANIFEST = PROJECT_ROOT / "target" / "manifest.json"

SAMPLE_ROWS = 8          # how many real rows to pull per upstream
CAPTURE_LIMIT = 5000     # max output rows to record as `expect`
_DECODER = json.JSONDecoder()


# --------------------------------------------------------------------------- #
# dbt show helper
# --------------------------------------------------------------------------- #
def show(sql: str, limit: int) -> list[dict]:
    """Run `dbt show --inline <sql> --output json` and return the rows.

    Tolerates surrounding log/deprecation noise by scanning stdout for the first
    JSON object that contains a `show` key.
    """
    proc = subprocess.run(
        ["dbt", "show", "--quiet", "--inline", sql,
         "--output", "json", "--limit", str(limit),
         "--vars", "ttd_enforce: false"],
        cwd=PROJECT_ROOT, capture_output=True, text=True,
    )
    out = proc.stdout
    i = out.find("{")
    while i != -1:
        try:
            obj, _ = _DECODER.raw_decode(out[i:])
            if isinstance(obj, dict) and "show" in obj:
                return obj["show"]
        except json.JSONDecodeError:
            pass
        i = out.find("{", i + 1)
    raise RuntimeError(f"could not parse `dbt show` output:\n{proc.stdout}\n{proc.stderr}")


# --------------------------------------------------------------------------- #
# manifest helpers
# --------------------------------------------------------------------------- #
def load_manifest() -> dict:
    if not MANIFEST.exists():
        sys.exit(f"manifest not found at {MANIFEST}. Run `dbt parse`/`dbt compile` first.")
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def models_with_unit_tests(manifest: dict) -> set[str]:
    covered: set[str] = set()
    for ut in manifest.get("unit_tests", {}).values():
        covered.update(
            d for d in ut.get("depends_on", {}).get("nodes", []) if d.startswith("model.")
        )
    for node in manifest["nodes"].values():
        if node.get("resource_type") == "unit_test":
            covered.update(
                d for d in node["depends_on"]["nodes"] if d.startswith("model.")
            )
    return covered


def upstream_ref(manifest: dict, uid: str) -> tuple[str, str]:
    """Return (relation_name, fixture_input_expr) for an upstream unique_id."""
    if uid in manifest["nodes"]:
        node = manifest["nodes"][uid]
        return node["relation_name"], f"ref('{node['name']}')"
    src = manifest["sources"][uid]
    return src["relation_name"], f"source('{src['source_name']}', '{src['name']}')"


# --------------------------------------------------------------------------- #
# SQL / value formatting
# --------------------------------------------------------------------------- #
def split_relation(relation_name: str) -> tuple[str, str, str]:
    parts = [p.strip('"') for p in relation_name.split(".")]
    return parts[-3], parts[-2], parts[-1]  # db, schema, table


def _full_type(row: dict) -> str:
    """Reconstruct a castable type. information_schema reports NUMBER without
    scale, so a bare `cast(x as NUMBER)` truncates decimals -- we must rebuild
    NUMBER(precision, scale) from the numeric_* columns."""
    dt = (row["DATA_TYPE"] or "").upper()
    if dt in ("NUMBER", "DECIMAL", "NUMERIC"):
        p, s = row.get("NUMERIC_PRECISION"), row.get("NUMERIC_SCALE")
        if p is not None:
            return f"NUMBER({int(p)},{int(s or 0)})"
        return "NUMBER"
    if dt in ("TEXT", "VARCHAR", "STRING", "CHAR", "CHARACTER"):
        return "VARCHAR"  # length-free avoids any truncation on cast
    return dt


def column_types(relation_name: str) -> dict[str, str]:
    db, schema, table = split_relation(relation_name)
    rows = show(
        "select column_name, data_type, numeric_precision, numeric_scale "
        f"from {db}.information_schema.columns "
        f"where table_schema = upper('{schema}') and table_name = upper('{table}') "
        f"order by ordinal_position",
        limit=10000,
    )
    return {r["COLUMN_NAME"].lower(): _full_type(r) for r in rows}


def sql_literal(value, data_type: str) -> str:
    if value is None:
        return f"cast(null as {data_type})"
    if isinstance(value, bool):
        return f"cast({'true' if value else 'false'} as {data_type})"
    if isinstance(value, (int, float)):
        return f"cast({value} as {data_type})"
    escaped = str(value).replace("'", "''")
    return f"cast('{escaped}' as {data_type})"


def build_cte(rows: list[dict], types: dict[str, str]) -> str:
    """A parenthesised subquery materialising `rows` with correct types."""
    cols = [c.lower() for c in rows[0].keys()]
    selects = []
    for idx, row in enumerate(rows):
        lowered = {k.lower(): v for k, v in row.items()}
        pieces = []
        for col in cols:
            lit = sql_literal(lowered.get(col), types.get(col, "varchar"))
            pieces.append(f"{lit} as {col}" if idx == 0 else lit)
        selects.append("select " + ", ".join(pieces))
    return "(\n  " + "\n  union all\n  ".join(selects) + "\n)"


# --------------------------------------------------------------------------- #
# YAML emission
# --------------------------------------------------------------------------- #
def yaml_scalar(value) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return repr(value)
    return "'" + str(value).replace("'", "''") + "'"


def yaml_row(row: dict) -> str:
    items = ", ".join(f"{k.lower()}: {yaml_scalar(v)}" for k, v in row.items())
    return "{" + items + "}"


def build_unit_test_yaml(model: str, inputs: list[tuple[str, list[dict]]],
                         expect: list[dict]) -> str:
    lines = [
        "# AUTO-GENERATED TTD CHARACTERIZATION UNIT TEST.",
        "# given = real sampled rows; expect = the model's actual output on them.",
        "# It locks in CURRENT behaviour: a change that alters output fails this test.",
        "# Review the assertions, then fold into the real _*__models.yml.",
        "version: 2",
        "",
        "unit_tests:",
        f"  - name: ut_{model}_characterization",
        f"    model: {model}",
        "    given:",
    ]
    for input_expr, rows in inputs:
        lines.append(f"      - input: {input_expr}")
        lines.append("        rows:")
        lines.extend(f"          - {yaml_row(r)}" for r in rows)
    lines.append("    expect:")
    lines.append("      rows:")
    lines.extend(f"        - {yaml_row(r)}" for r in expect)
    lines.append("")
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# core
# --------------------------------------------------------------------------- #
def generate_for(manifest: dict, node: dict) -> str:
    """Return a status string; write the unit-test file as a side effect."""
    name = node["name"]
    compiled = node.get("compiled_code")
    if not compiled:
        return f"  ! {name}: no compiled_code (run a build/compile first) -- skipped"

    upstreams = [u for u in node["depends_on"]["nodes"]]
    if not upstreams:
        return f"  ! {name}: no upstream refs -- skipped (nothing to mock)"

    capture_sql = compiled
    inputs: list[tuple[str, list[dict]]] = []
    for uid in upstreams:
        relation, input_expr = upstream_ref(manifest, uid)
        if relation not in capture_sql:
            return (f"  ! {name}: upstream relation {relation} not found verbatim in "
                    f"compiled SQL -- fell back to skeleton")
        types = column_types(relation)
        rows = show(f"select * from {relation}", limit=SAMPLE_ROWS)
        if not rows:
            return f"  ! {name}: upstream {relation} returned no sample rows -- skipped"
        cte = build_cte(rows, types)
        capture_sql = capture_sql.replace(relation, f"{cte} as ttd_mock", 1)
        inputs.append((input_expr, rows))

    expect = show(capture_sql, limit=CAPTURE_LIMIT)
    if not expect:
        return (f"  ! {name}: sampled rows produced no output (filter/join) -- "
                f"fell back to skeleton")

    stub_path = (PROJECT_ROOT / node["original_file_path"]).parent / f"_ttd_unit__{name}.yml"
    stub_path.write_text(build_unit_test_yaml(name, inputs, expect), encoding="utf-8")
    return f"  + unit test created: {name} ({len(inputs)} input(s), {len(expect)} expect row(s))"


def main(argv: list[str] | None = None) -> int:
    only = set(argv or [])  # if given, restrict generation to these model names
    manifest = load_manifest()
    covered = models_with_unit_tests(manifest)
    project = manifest["metadata"]["project_name"]

    print("TTD unit-test generation")
    print("-" * 24)
    any_done = False
    for uid, node in manifest["nodes"].items():
        if node.get("resource_type") != "model" or node.get("package_name") != project:
            continue
        if uid in covered:
            continue
        if only and node["name"] not in only:
            continue
        name = node["name"]
        stub_path = (PROJECT_ROOT / node["original_file_path"]).parent / f"_ttd_unit__{name}.yml"
        if stub_path.exists():
            print(f"  = unit test already exists (skipped): {name}")
            any_done = True
            continue
        try:
            print(generate_for(manifest, node))
        except Exception as exc:  # noqa: BLE001 -- honest fallback, never block the build
            print(f"  ! {name}: generation error ({exc}) -- fell back to skeleton")
        any_done = True

    if not any_done:
        print("  All models already have unit tests. Nothing to generate.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

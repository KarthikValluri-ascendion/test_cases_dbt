"""TTD scaffolder: generate test stubs for dbt models that have none.

Reads target/manifest.json (produced by `dbt parse`), finds every model that
no test/unit_test depends on, and writes a YAML stub next to the model with:
  - not_null + unique on key-like columns (heuristic: name ends in _key/_id)
  - not_null on every other column
  - a commented native unit_test skeleton to fill in

Columns are taken from the manifest when documented, otherwise extracted from
the model SQL's `... as <alias>` clauses (works for explicitly-aliased models).

This is the "scaffold" half of TTD. It never overwrites an existing stub and
never edits a hand-written properties file -- it only creates `_ttd_stub__*.yml`.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
MANIFEST = PROJECT_ROOT / "target" / "manifest.json"

ALIAS_RE = re.compile(r"\bas\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*(?:,|\n|$)", re.IGNORECASE)


def load_manifest() -> dict:
    if not MANIFEST.exists():
        sys.exit(f"manifest not found at {MANIFEST}. Run `dbt parse` first.")
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def covered_model_ids(manifest: dict) -> set[str]:
    """unique_ids of models that at least one test or unit_test depends on."""
    covered: set[str] = set()
    for node in manifest["nodes"].values():
        if node["resource_type"] in ("test", "unit_test"):
            covered.update(
                d for d in node["depends_on"]["nodes"] if d.startswith("model.")
            )
    # unit_tests live under a separate top-level key in some dbt versions
    for ut in manifest.get("unit_tests", {}).values():
        covered.update(
            d for d in ut.get("depends_on", {}).get("nodes", []) if d.startswith("model.")
        )
    return covered


def columns_for(node: dict) -> list[str]:
    """Documented columns if present, else aliases parsed from the SQL."""
    if node.get("columns"):
        return list(node["columns"].keys())
    sql = node.get("raw_code", "")
    # de-dupe while preserving order
    seen, cols = set(), []
    for m in ALIAS_RE.finditer(sql):
        c = m.group(1).lower()
        if c not in seen:
            seen.add(c)
            cols.append(c)
    return cols


def is_key(col: str) -> bool:
    return col.endswith("_key") or col.endswith("_id")


def build_stub(name: str, description: str, columns: list[str]) -> str:
    lines = [
        "# AUTO-GENERATED TTD STUB -- review, then fold into the real _*__models.yml.",
        "# Heuristic tests only. Tighten them, then delete this banner.",
        "version: 2",
        "",
        "models:",
        f"  - name: {name}",
        f'    description: "TODO: describe {name}."',
    ]
    if columns:
        lines.append("    columns:")
        for col in columns:
            lines.append(f"      - name: {col}")
            if is_key(col):
                lines.append("        data_tests: [not_null, unique]")
            else:
                lines.append("        data_tests: [not_null]")
    lines += [
        "",
        "# unit_tests:",
        f"#   - name: ut_{name}_TODO",
        f"#     model: {name}",
        "#     given:",
        "#       - input: ref('TODO_upstream_model')",
        "#         rows:",
        "#           - {col: value}",
        "#     expect:",
        "#       rows:",
        "#         - {col: value}",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    manifest = load_manifest()
    covered = covered_model_ids(manifest)
    project = manifest["metadata"]["project_name"]

    created, already = [], []
    for uid, node in manifest["nodes"].items():
        if node["resource_type"] != "model":
            continue
        if node["package_name"] != project:
            continue
        if uid in covered:
            continue

        name = node["name"]
        model_path = PROJECT_ROOT / node["original_file_path"]
        stub_path = model_path.parent / f"_ttd_stub__{name}.yml"
        if stub_path.exists():
            already.append(name)
            continue

        cols = columns_for(node)
        stub_path.write_text(
            build_stub(name, node.get("description", ""), cols), encoding="utf-8"
        )
        created.append((name, len(cols)))

    print("TTD scaffold summary")
    print("-" * 20)
    if not created and not already:
        print("All models already have tests. Nothing to scaffold.")
    for name, ncols in created:
        print(f"  + stub created: {name} ({ncols} columns)")
    for name in already:
        print(f"  = stub already exists (skipped): {name}")
    print(f"\n{len(created)} stub(s) created, {len(already)} skipped.")
    if created:
        print("\nNext: review the _ttd_stub__*.yml files, then run `dbt build`.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

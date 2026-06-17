"""TTD executive dashboard generator -- a single self-contained local HTML file
(no server, no CDN, opens offline in any browser).

Mirrors the look of the PI -> FTL executive dashboards (dark hero, KPI tiles,
inline SVG charts, tabbed layout) but tells the TTD (Test-Then-Deploy) story for
this medallion dbt project. Five tabs:

  1. Executive Summary - business KPIs from the GOLD layer (orders, revenue,
     customers, high-value orders) + revenue-by-region + monthly revenue trend.
  2. Test Coverage     - the TTD scorecard: every model, its layer, and the
     functional / singular / unit tests that gate its deploy (PASS / UNTESTED).
  3. Lineage           - the medallion DAG: TPC-H source -> bronze -> silver ->
     gold -> consumers, built live from the dbt manifest.
  4. Tokenomics        - cost of the AI-assisted build of this project: tokens,
     model, run time, $ cost, ROI vs a manual baseline. Driven by the editable
     artifacts/ttd_telemetry.json (token figures are estimates).
  5. Workflow          - the TTD cycle: scaffold -> coverage gate -> build ->
     gen-unit-tests -> test.

Data sources:
  - Coverage / lineage / inventory come from target/manifest.json (run `dbt parse`
    first; the ttd.py `dashboard` subcommand does this for you).
  - Business KPIs are queried LIVE from the built GOLD tables via `dbt show`
    (same warehouse connection as the unit-test generator), so the gold models
    must already be built (`python ttd.py build`).

Side effect: also writes supporting evidence files into artifacts/ (CSV extracts,
a coverage report in md + csv, a model inventory, and run_telemetry.json), the
same way the PI runs produced an artifacts library.

Usage:
  python ttd/build_dashboard.py [--product "TTD Medallion"] [--database DB01]
"""
from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
from datetime import datetime, timezone
from html import escape
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
MANIFEST = PROJECT_ROOT / "target" / "manifest.json"
ART = PROJECT_ROOT / "artifacts"
TELEMETRY_PATH = ART / "ttd_telemetry.json"
_DECODER = json.JSONDecoder()

LAYER_ORDER = {"bronze": 0, "silver": 1, "gold": 2}
GOLD_MODELS = ("fct_orders", "fct_high_value_orders", "dim_customers")

# Claude per-1M-token pricing (input, output), USD. Source: claude-api skill table.
PRICING = {
    "claude-opus-4-8": (5.0, 25.0),
    "claude-fable-5": (10.0, 50.0),
    "claude-sonnet-4-6": (3.0, 15.0),
    "claude-haiku-4-5": (1.0, 5.0),
}
MODEL_LABEL = {
    "claude-opus-4-8": "Claude Opus 4.8", "claude-fable-5": "Claude Fable 5",
    "claude-sonnet-4-6": "Claude Sonnet 4.6", "claude-haiku-4-5": "Claude Haiku 4.5",
}

# Default tokenomics telemetry for the AI-assisted build of this TTD project.
# Token figures are ESTIMATES (the harness exposes no exact per-step counters) --
# seeded into artifacts/ttd_telemetry.json on first run so you can edit with actuals.
DEFAULT_TELEMETRY = {
    "model_used": {"orchestrator": "claude-opus-4-8"},
    "totals_est": {"tokens_input_est": 178000, "tokens_output_est": 46000,
                   "wall_clock_minutes": 24, "story_points": 8},
    "steps": [
        {"step": "1", "title": "Explore PI reference + TTD project",
         "tokens_est": {"input": 58000, "output": 7000}},
        {"step": "2", "title": "Design the dashboard generator",
         "tokens_est": {"input": 34000, "output": 9000}},
        {"step": "3", "title": "Write build_dashboard.py",
         "tokens_est": {"input": 32000, "output": 16000}},
        {"step": "4", "title": "Wire ttd.py subcommand + plugin skill",
         "tokens_est": {"input": 24000, "output": 8000}},
        {"step": "5", "title": "Run, verify, and capture artifacts",
         "tokens_est": {"input": 30000, "output": 6000}},
    ],
    "note": "Token figures are ESTIMATES; the harness does not expose exact per-step "
            "counters. Edit this file with actuals to refresh the Tokenomics tab.",
}


# --------------------------------------------------------------------------- #
# dbt show helper (robust JSON scan -- copied pattern from generate_unit_tests.py)
# --------------------------------------------------------------------------- #
def show(sql: str, limit: int = 10000) -> list[dict]:
    """Run `dbt show --inline <sql> --output json` and return rows as dicts with
    lower-cased keys. Tolerates surrounding log/deprecation noise."""
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
                return [{k.lower(): v for k, v in r.items()} for r in obj["show"]]
        except json.JSONDecodeError:
            pass
        i = out.find("{", i + 1)
    raise RuntimeError(f"could not parse `dbt show` output:\n{proc.stdout}\n{proc.stderr}")


def q1(sql: str) -> dict:
    rows = show(sql, limit=1)
    return rows[0] if rows else {}


# --------------------------------------------------------------------------- #
# value formatting
# --------------------------------------------------------------------------- #
def num(v) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def fmt_int(n) -> str:
    try:
        return f"{int(round(num(n))):,}"
    except (TypeError, ValueError):
        return "-"


def money(n) -> str:
    """Whole dollars with thousands separators."""
    return f"${num(n):,.0f}"


def money2(n) -> str:
    """Dollars with cents -- for small AI-run costs (tokens)."""
    return f"${num(n):,.2f}"


def money_compact(n) -> str:
    """Compact dollars for KPI tiles: $1.23B / $45.6M / $789K / $123."""
    v = num(n)
    a = abs(v)
    if a >= 1e9:
        return f"${v / 1e9:.2f}B"
    if a >= 1e6:
        return f"${v / 1e6:.1f}M"
    if a >= 1e3:
        return f"${v / 1e3:.0f}K"
    return f"${v:,.0f}"


def _write_csv(path: Path, header: list[str], rows: list) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(header)
        for r in rows:
            w.writerow(["" if v is None else v for v in r])


# --------------------------------------------------------------------------- #
# manifest -> coverage / lineage
# --------------------------------------------------------------------------- #
def load_manifest() -> dict:
    if not MANIFEST.exists():
        sys.exit(f"manifest not found at {MANIFEST}. Run `dbt parse` first "
                 f"(the ttd.py `dashboard` subcommand does this).")
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def _test_kind(node: dict) -> str:
    """A short label for the test kind, used for footer badges + reporting."""
    meta = node.get("test_metadata")
    if not meta:
        return "singular"
    name = meta.get("name", "")
    ns = meta.get("namespace")
    return f"{ns}.{name}" if ns else name


def compute_coverage(manifest: dict) -> tuple[list[dict], set[str]]:
    """Return (per-model coverage rows, set of all test-kind labels seen)."""
    project = manifest["metadata"]["project_name"]

    models: dict[str, dict] = {}
    for uid, node in manifest["nodes"].items():
        if node.get("resource_type") != "model" or node.get("package_name") != project:
            continue
        models[uid] = {
            "uid": uid,
            "name": node["name"],
            "layer": node["fqn"][1] if len(node["fqn"]) > 2 else "-",
            "materialized": node["config"].get("materialized", "-"),
            "data": 0, "singular": 0, "unit": 0, "kinds": [],
        }

    kinds_seen: set[str] = set()

    # schema (generic) + singular tests
    for uid, node in manifest["nodes"].items():
        if node.get("resource_type") != "test" or node.get("package_name") != project:
            continue
        kind = _test_kind(node)
        kinds_seen.add(kind)
        # generic tests carry attached_node; singular ones list the model in depends_on
        targets = []
        attached = node.get("attached_node")
        if attached and attached in models:
            targets = [attached]
        else:
            targets = [d for d in node["depends_on"]["nodes"] if d in models]
        bucket = "data" if node.get("test_metadata") else "singular"
        for t in targets:
            models[t][bucket] += 1
            models[t]["kinds"].append(kind)

    # unit tests (manifest.unit_tests dict in dbt >=1.8)
    for ut in manifest.get("unit_tests", {}).values():
        kinds_seen.add("unit")
        for d in ut.get("depends_on", {}).get("nodes", []):
            if d in models:
                models[d]["unit"] += 1
                models[d]["kinds"].append("unit")
    # ...and any unit_test resource nodes (older layouts)
    for node in manifest["nodes"].values():
        if node.get("resource_type") != "unit_test":
            continue
        kinds_seen.add("unit")
        for d in node["depends_on"]["nodes"]:
            if d in models:
                models[d]["unit"] += 1
                models[d]["kinds"].append("unit")

    rows = []
    for m in models.values():
        m["total"] = m["data"] + m["singular"] + m["unit"]
        m["covered"] = m["total"] > 0
        rows.append(m)
    rows.sort(key=lambda r: (LAYER_ORDER.get(r["layer"], 9), r["name"]))
    return rows, kinds_seen


def relation_of(manifest: dict, model_name: str) -> str | None:
    project = manifest["metadata"]["project_name"]
    for node in manifest["nodes"].values():
        if (node.get("resource_type") == "model" and node.get("package_name") == project
                and node["name"] == model_name):
            return node.get("relation_name")
    return None


def _kscalar(v) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    return str(v)


def _klistitem(v) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, str):
        return f"'{v}'"
    return str(v)


def _yval(v) -> str:
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return repr(v)
    return f"'{v}'"


def _yrow(row: dict) -> str:
    return "{" + ", ".join(f"{k}: {_yval(v)}" for k, v in row.items()) + "}"


def _generic_code(node: dict) -> str:
    """Reconstruct the test definition exactly as written in the schema yml."""
    meta = node["test_metadata"]
    col = meta["kwargs"].get("column_name")
    ns = meta.get("namespace")
    full = f"{ns}.{meta['name']}" if ns else meta["name"]
    args = {k: v for k, v in meta["kwargs"].items() if k not in ("column_name", "model")}
    lines = [f"# {node.get('original_file_path', '')}"]
    if col:
        lines += ["columns:", f"  - name: {col}", "    data_tests:"]
        indent = "      "
    else:
        lines += ["data_tests:"]
        indent = "  "
    if not args:
        lines.append(f"{indent}- {full}")
    else:
        lines.append(f"{indent}- {full}:")
        for k, v in args.items():
            if isinstance(v, list):
                lines.append(f"{indent}    {k}: [" + ", ".join(_klistitem(x) for x in v) + "]")
            else:
                lines.append(f"{indent}    {k}: {_kscalar(v)}")
    return "\n".join(lines)


def _singular_code(node: dict) -> str:
    return f"# {node.get('original_file_path', '')}\n" + (node.get("raw_code") or "")


def _unit_code(ut: dict) -> str:
    lines = [f"# unit test (characterization)", "unit_tests:",
             f"  - name: {ut['name']}", f"    model: {ut.get('model')}", "    given:"]
    for g in ut.get("given", []):
        lines.append(f"      - input: {g.get('input')}")
        lines.append("        rows:")
        for r in g.get("rows", []):
            lines.append(f"          - {_yrow(r)}")
    lines.append("    expect:")
    lines.append("      rows:")
    for r in ut.get("expect", {}).get("rows", []):
        lines.append(f"        - {_yrow(r)}")
    return "\n".join(lines)


def build_test_details(manifest: dict, model_uids: dict[str, str]) -> dict:
    """{model_name: {schema:[...], singular:[...], unit:[...]}} where each test is
    {name, kind, code} -- code is the test's definition as written. model_uids maps
    model unique_id -> model name."""
    project = manifest["metadata"]["project_name"]
    out = {name: {"schema": [], "singular": [], "unit": []} for name in model_uids.values()}

    for node in manifest["nodes"].values():
        if node.get("resource_type") != "test" or node.get("package_name") != project:
            continue
        if node.get("test_metadata"):
            attached = node.get("attached_node")
            tgt = attached if attached in model_uids else \
                next((d for d in node["depends_on"]["nodes"] if d in model_uids), None)
            if tgt:
                out[model_uids[tgt]]["schema"].append(
                    {"name": node["name"], "kind": _test_kind(node), "code": _generic_code(node)})
        else:
            tgt = next((d for d in node["depends_on"]["nodes"] if d in model_uids), None)
            if tgt:
                out[model_uids[tgt]]["singular"].append(
                    {"name": node["name"], "kind": "singular", "code": _singular_code(node)})

    for ut in manifest.get("unit_tests", {}).values():
        tgt = next((d for d in ut.get("depends_on", {}).get("nodes", []) if d in model_uids), None)
        if tgt:
            out[model_uids[tgt]]["unit"].append(
                {"name": ut["name"], "kind": "unit", "code": _unit_code(ut)})
    return out


def lineage_stages(manifest: dict, coverage_rows: list[dict]) -> list[tuple]:
    """Build the medallion flow from the manifest: source -> bronze -> silver -> gold."""
    by_layer: dict[str, list[str]] = {"bronze": [], "silver": [], "gold": []}
    for r in coverage_rows:
        if r["layer"] in by_layer:
            by_layer[r["layer"]].append(r["name"])
    sources = sorted({s["name"] for s in manifest["sources"].values()})
    return [
        ("Source · TPC-H", sources, "SNOWFLAKE_SAMPLE_DATA share (read-only)", "before"),
        ("Bronze · view", by_layer["bronze"], "raw passthrough, typed", "before"),
        ("Silver · view", by_layer["silver"], "cleaned + conformed; explicit revenue math", "mid"),
        ("Gold · table", by_layer["gold"], "business-facing facts + dimension", "after"),
        ("Consumers", ["BI / this exec dashboard"], "tests gate every deploy", "after"),
    ]


# --------------------------------------------------------------------------- #
# inline SVG charts (no external deps -- ported from the PI dashboard)
# --------------------------------------------------------------------------- #
def svg_area(series, w=720, h=240, pad=34, accent="#6366f1") -> str:
    if not series:
        return "<svg></svg>"
    vals = [v for _, v in series]
    vmax = max(vals) or 1
    n = len(series)
    iw, ih = w - 2 * pad, h - 2 * pad
    xs = [pad + (iw * i / (n - 1 if n > 1 else 1)) for i in range(n)]
    ys = [pad + ih - (ih * (v / vmax)) for v in vals]
    pts = " ".join(f"{x:.1f},{y:.1f}" for x, y in zip(xs, ys))
    area = f"{pad},{pad+ih} " + pts + f" {pad+iw:.1f},{pad+ih}"
    grid = "".join(
        f'<line x1="{pad}" y1="{pad+ih*g/4:.1f}" x2="{pad+iw}" y2="{pad+ih*g/4:.1f}" '
        f'stroke="#eef0f6" stroke-width="1"/>' for g in range(5))
    dots = "".join(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3.5" fill="#fff" '
                   f'stroke="{accent}" stroke-width="2.5"/>' for x, y in zip(xs, ys))
    labels = "".join(
        f'<text x="{x:.1f}" y="{h-10}" text-anchor="middle" class="ax">{escape(str(lbl))}</text>'
        for x, (lbl, _) in zip(xs, series))
    ymax_lbl = f'<text x="6" y="{pad+6}" class="ax">{money_compact(vmax)}</text>'
    return f"""<svg viewBox="0 0 {w} {h}" class="chart" preserveAspectRatio="xMidYMid meet">
  <defs><linearGradient id="agrad" x1="0" x2="0" y1="0" y2="1">
    <stop offset="0%" stop-color="{accent}" stop-opacity="0.35"/>
    <stop offset="100%" stop-color="{accent}" stop-opacity="0.02"/></linearGradient></defs>
  {grid}{ymax_lbl}
  <polygon points="{area}" fill="url(#agrad)"/>
  <polyline points="{pts}" fill="none" stroke="{accent}" stroke-width="3"
    stroke-linejoin="round" stroke-linecap="round"/>
  {dots}{labels}
</svg>"""


def svg_bars(series, w=720, barh=30, gap=14, pad=8, accent="#6366f1",
             fmt=fmt_int) -> str:
    if not series:
        return "<svg></svg>"
    vmax = max(v for _, v in series) or 1
    labw = 168
    iw = w - labw - 90
    h = pad * 2 + len(series) * (barh + gap)
    rows = []
    for i, (lbl, v) in enumerate(series):
        y = pad + i * (barh + gap)
        bw = max(2, iw * (v / vmax))
        rows.append(
            f'<text x="{labw-10}" y="{y+barh*0.66:.0f}" text-anchor="end" class="bl">{escape(str(lbl))}</text>'
            f'<rect x="{labw}" y="{y}" width="{bw:.1f}" height="{barh}" rx="6" fill="url(#bgrad)"/>'
            f'<text x="{labw+bw+8:.1f}" y="{y+barh*0.66:.0f}" class="bv">{escape(fmt(v))}</text>')
    return f"""<svg viewBox="0 0 {w} {h}" class="chart" preserveAspectRatio="xMidYMid meet">
  <defs><linearGradient id="bgrad" x1="0" x2="1" y1="0" y2="0">
    <stop offset="0%" stop-color="{accent}"/><stop offset="100%" stop-color="#22c55e"/></linearGradient></defs>
  {''.join(rows)}
</svg>"""


# --------------------------------------------------------------------------- #
# HTML fragment builders
# --------------------------------------------------------------------------- #
def _flow_html(stages) -> str:
    cards = []
    for i, (title, nodes, note, tone) in enumerate(stages):
        chips = "".join(f'<span class="node">{escape(n)}</span>' for n in nodes) or \
            '<span class="node">-</span>'
        cards.append(
            f'<div class="stage {tone}"><div class="stage-h">{escape(title)}</div>'
            f'<div class="nodes">{chips}</div><div class="stage-note">{escape(note)}</div></div>')
        if i < len(stages) - 1:
            cards.append('<div class="arrow">&rarr;</div>')
    return f'<div class="flow">{"".join(cards)}</div>'


def _numcell(model: str, cat: str, n: int, extra: str = "") -> str:
    """A coverage count: a clickable link to its test definitions when n > 0."""
    cls = f"num {extra}".strip()
    if n > 0:
        return (f'<td class="{cls}"><a class="tlink" href="#" data-m="{escape(model)}" '
                f'data-c="{cat}">{n}</a></td>')
    return f'<td class="{cls}">{n}</td>'


def _coverage_rows_html(rows) -> str:
    out = ""
    for r in rows:
        badge = "pass" if r["covered"] else "flag"
        status = "PASS" if r["covered"] else "UNTESTED"
        m = r["name"]
        out += (f'<tr><td class="metric">{escape(m)}</td>'
                f'<td><span class="lyr {r["layer"]}">{escape(r["layer"])}</span></td>'
                f'<td>{escape(r["materialized"])}</td>'
                f'{_numcell(m, "schema", r["data"])}'
                f'{_numcell(m, "singular", r["singular"])}'
                f'{_numcell(m, "unit", r["unit"])}'
                f'{_numcell(m, "all", r["total"], extra="dev")}'
                f'<td><span class="badge {badge}">{status}</span></td></tr>')
    return out


def _kpi_html(kpis) -> str:
    html = ""
    for k in kpis:
        dc = f' data-count="{int(k["data"])}"' if k.get("data") is not None else ""
        html += (f'<div class="kpi"><div class="kpi-label">{escape(k["label"])}</div>'
                 f'<div class="kpi-val"{dc}>{escape(k["value"])}</div>'
                 f'<div class="kpi-sub {k.get("cls","flat")}">{escape(k["sub"])}</div></div>')
    return html


# ---- Workflow tab (the TTD cycle; inline-styled like the PI workflow tab) -------
_WF_CHIP = {
    "cmd":  "background:#eef2ff;color:#4338ca;",
    "gate": "background:#fff7ed;color:#c2410c;border:1px solid #fed7aa;",
    "test": "background:#ecfdf5;color:#047857;",
    "none": "background:#f1f5f9;color:#64748b;",
}


def _wf_chip(text, kind) -> str:
    return (f'<span style="{_WF_CHIP[kind]}font-size:12px;font-weight:700;padding:5px 11px;'
            f'border-radius:8px;margin:3px 6px 3px 0;display:inline-block;">{escape(text)}</span>')


def _wf_legend_item(color, label) -> str:
    return (f'<span style="display:inline-flex;align-items:center;gap:7px;font-size:13px;font-weight:600;margin-right:18px;">'
            f'<span style="width:13px;height:13px;border-radius:4px;background:{color};display:inline-block;"></span>{escape(label)}</span>')


def _wf_row(num_, label, title, chips, gate) -> str:
    bd = "#f59e0b" if gate else "#6366f1"
    cl = "#b45309" if gate else "#4f46e5"
    chips_html = "".join(_wf_chip(t, k) for t, k in chips)
    return (f'<div style="display:flex;gap:14px;margin-bottom:12px;">'
            f'<div style="flex:0 0 48px;height:48px;width:48px;border-radius:50%;background:#fff;'
            f'border:3px solid {bd};color:{cl};font-weight:800;font-size:16px;display:flex;'
            f'align-items:center;justify-content:center;box-shadow:0 8px 18px -10px rgba(79,70,229,.5);">{escape(str(num_))}</div>'
            f'<div style="flex:1;background:#fff;border-radius:12px;padding:12px 16px;border:1px solid #e8eaf3;'
            f'box-shadow:0 14px 30px -26px rgba(2,6,23,.5);">'
            f'<div style="font-size:15px;font-weight:700;margin-bottom:7px;">'
            f'<span style="color:#94a3b8;font-size:12px;margin-right:8px;letter-spacing:.4px;">{escape(label)}</span>{escape(title)}</div>'
            f'<div>{chips_html}</div></div></div>')


_WF_STEPS = [
    ("1", "SCAFFOLD", "Generate functional (not_null / unique) test stubs for any untested model",
     [("python ttd.py scaffold", "cmd"), ("pre-build · no warehouse", "none")], False),
    ("2", "ENFORCE", "Coverage gate runs on-run-start; aborts the build if any model has zero tests",
     [("ttd_enforce_coverage()", "cmd"), ("COVERAGE GATE", "gate")], True),
    ("3", "BUILD", "dbt build -- models materialise + all schema/singular tests run",
     [("dbt build", "cmd"), ("not_null · unique · accepted_range · relationships", "test")], False),
    ("4", "GEN UNIT TESTS", "Sample real rows, run the model's compiled SQL, capture given -> expect",
     [("python ttd.py gen-unit-tests", "cmd"), ("characterization", "test")], False),
    ("5", "TEST", "Run the generated characterization unit tests",
     [("dbt test --select test_type:unit", "cmd"), ("unit", "test")], False),
]


def _build_workflow_html(stats) -> str:
    rows = "".join(_wf_row(*s) for s in _WF_STEPS)
    legend = (_wf_legend_item("#6366f1", "TTD command / dbt step")
              + _wf_legend_item("#f59e0b", "Coverage gate (blocks deploy)")
              + _wf_legend_item("#10b981", "Tests that run"))
    stat_html = "".join(
        f'<div style="flex:1;min-width:140px;background:#f8fafc;border:1px solid #eef0f6;border-radius:12px;'
        f'padding:14px;text-align:center;"><div style="font-size:24px;font-weight:800;color:#4f46e5;">{escape(str(n))}</div>'
        f'<div style="font-size:12px;color:#64748b;font-weight:600;margin-top:2px;">{escape(l)}</div></div>'
        for n, l in stats)
    return (f'<div class="card"><h2>The Test-Then-Deploy cycle</h2>'
            f'<p class="lead">No model reaches production untested. The coverage gate runs <b>before</b> the build '
            f'and aborts it if any model has zero tests; <code>ttd.py</code> then scaffolds the missing tests, builds, '
            f'and back-fills a characterization unit test from real warehouse rows.</p>'
            f'<div style="margin:4px 0 18px;">{legend}</div>{rows}</div>'
            f'<div class="card"><h2>Current state</h2>'
            f'<div style="display:flex;gap:12px;flex-wrap:wrap;">{stat_html}</div></div>')


# ---- Tokenomics tab (AI-assisted build cost; ported from the PI dashboard) -----
def load_telemetry() -> dict:
    """Read artifacts/ttd_telemetry.json, seeding it with editable defaults on
    first run. Token figures are estimates -- see the file's `note`."""
    try:
        return json.loads(TELEMETRY_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        ART.mkdir(exist_ok=True)
        TELEMETRY_PATH.write_text(json.dumps(DEFAULT_TELEMETRY, indent=2), encoding="utf-8")
        return DEFAULT_TELEMETRY


def _orchestrator_model(tel: dict) -> str:
    s = (tel or {}).get("model_used", {}).get("orchestrator", "")
    for mid in PRICING:
        if mid in s:
            return mid
    return "claude-opus-4-8"


def build_tokenomics(tel: dict, model_id: str, labor_rate: float):
    """Return (kpi_html, models_html, steps_html, roi_html)."""
    in_rate, out_rate = PRICING.get(model_id, PRICING["claude-opus-4-8"])
    t = (tel or {}).get("totals_est", {})
    in_tok = num(t.get("tokens_input_est"))
    out_tok = num(t.get("tokens_output_est"))
    minutes = t.get("wall_clock_minutes", 0)
    points = num(t.get("story_points")) or 8
    cost_in = in_tok / 1e6 * in_rate
    cost_out = out_tok / 1e6 * out_rate
    cost = cost_in + cost_out

    kpis = [
        {"label": "AI run cost", "value": money2(cost), "sub": "Anthropic tokens"},
        {"label": "Input tokens", "value": fmt_int(in_tok), "data": in_tok, "sub": f"@ ${in_rate:g}/1M"},
        {"label": "Output tokens", "value": fmt_int(out_tok), "data": out_tok, "sub": f"@ ${out_rate:g}/1M"},
        {"label": "Wall-clock", "value": f"{fmt_int(minutes)} min", "sub": "agent execution"},
    ]
    kpi_html = _kpi_html(kpis)

    models_html = (f'<tr><td class="metric">{escape(MODEL_LABEL.get(model_id, model_id))}</td>'
                   f'<td>orchestrator (every step)</td>'
                   f'<td class="num">${in_rate:g} / ${out_rate:g}</td></tr>')

    steps_html = ""
    for s in (tel or {}).get("steps", []):
        te = s.get("tokens_est", {})
        si, so = num(te.get("input")), num(te.get("output"))
        sc = si / 1e6 * in_rate + so / 1e6 * out_rate
        steps_html += (f'<tr><td class="num">{escape(str(s.get("step", "")))}</td>'
                       f'<td>{escape(str(s.get("title", ""))[:46])}</td>'
                       f'<td class="num">{int(si)//1000}k</td><td class="num">{int(so)//1000}k</td>'
                       f'<td class="num">{money2(sc)}</td></tr>')

    manual_hrs = points
    saved_hrs = round(points * 0.6, 1)
    manual_cost = manual_hrs * labor_rate
    saved_cost = saved_hrs * labor_rate
    value_multiple = (saved_cost / cost) if cost else 0
    roi_html = f"""
      <div class="roi-grid">
        <div class="roi"><div class="roi-n">{fmt_int(manual_hrs)} hrs</div><div class="roi-l">Manual baseline ({int(points)} story pts)</div></div>
        <div class="roi"><div class="roi-n">{saved_hrs} hrs</div><div class="roi-l">Est. time saved (60%)</div></div>
        <div class="roi"><div class="roi-n">{money(manual_cost)}</div><div class="roi-l">Manual labor cost @ ${labor_rate:g}/hr</div></div>
        <div class="roi"><div class="roi-n">{money(saved_cost)}</div><div class="roi-l">Labor $ saved</div></div>
        <div class="roi accent"><div class="roi-n">{money2(cost)}</div><div class="roi-l">AI run cost (tokens)</div></div>
        <div class="roi accent"><div class="roi-n">{value_multiple:,.0f}&times;</div><div class="roi-l">Labor saved &divide; AI cost</div></div>
      </div>
      <p class="lead">Input/output cost split: <b>{money2(cost_in)}</b> / <b>{money2(cost_out)}</b>.
        Token figures are <b>estimates</b> from <code>artifacts/ttd_telemetry.json</code>; labor rate is an
        assumption (<code>--labor-rate</code>, default $100/hr). Edit the JSON with actuals to refresh this tab.</p>"""
    return kpi_html, models_html, steps_html, roi_html


# --------------------------------------------------------------------------- #
# static CSS / JS (inserted as values so their braces need no escaping)
# --------------------------------------------------------------------------- #
CSS = """
  :root { --bg:#0b1020; --card:#fff; --ink:#0f172a; --muted:#64748b;
    --indigo:#6366f1; --green:#22c55e; --amber:#f59e0b; --red:#ef4444; }
  * { box-sizing:border-box; }
  body { margin:0; font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
    color:var(--ink); background:#f1f5f9; -webkit-font-smoothing:antialiased; }
  .wrap { max-width:1120px; margin:0 auto; padding:0 22px 60px; }
  .hero { background:radial-gradient(1200px 500px at 15% -20%,#4f46e5 0%,#0b1020 60%),
    linear-gradient(135deg,#111827,#0b1020); color:#fff; padding:50px 0 120px; position:relative; overflow:hidden; }
  .hero::after { content:""; position:absolute; right:-120px; top:-120px; width:420px; height:420px;
    background:radial-gradient(circle,#6366f1 0%,transparent 65%); opacity:.45; }
  .hero .wrap { position:relative; z-index:1; }
  .eyebrow { letter-spacing:.32em; text-transform:uppercase; font-size:12px; color:#a5b4fc; font-weight:700; }
  h1 { font-size:40px; margin:10px 0 6px; font-weight:800; letter-spacing:-.5px; }
  .sub { color:#cbd5e1; font-size:15.5px; max-width:680px; line-height:1.5; }
  .pill { display:inline-flex; align-items:center; gap:8px; margin-top:16px; padding:8px 16px;
    background:rgba(34,197,94,.16); border:1px solid rgba(34,197,94,.5); color:#bbf7d0;
    border-radius:999px; font-weight:700; font-size:13px; }
  .dot { width:9px; height:9px; border-radius:50%; background:var(--green); box-shadow:0 0 12px #22c55e; }
  .tabs { position:relative; z-index:2; display:flex; gap:8px; margin-top:22px; flex-wrap:wrap; }
  .tab { appearance:none; border:1px solid #e2e8f0; background:#fff; color:#334155; font-weight:700;
    font-size:14px; padding:10px 18px; border-radius:12px; cursor:pointer; box-shadow:0 10px 24px -18px rgba(2,6,23,.5);
    transition:transform .15s, background .15s, color .15s; }
  .tab:hover { transform:translateY(-2px); }
  .tab.active { background:#4f46e5; color:#fff; border-color:#4f46e5; }
  .panel { display:none; } .panel.active { display:block; }
  .grid { position:relative; z-index:2; margin-top:18px; display:grid; grid-template-columns:repeat(4,1fr); gap:18px; }
  .kpi { background:var(--card); border-radius:18px; padding:22px 20px;
    box-shadow:0 18px 40px -22px rgba(2,6,23,.45); border:1px solid #eef0f6;
    transition:transform .2s ease, box-shadow .2s ease; }
  .kpi:hover { transform:translateY(-4px); box-shadow:0 26px 50px -20px rgba(2,6,23,.5); }
  .kpi-label { color:var(--muted); font-size:12.5px; font-weight:700; text-transform:uppercase; letter-spacing:.06em; }
  .kpi-val { font-size:32px; font-weight:800; margin:8px 0 6px; letter-spacing:-.5px; }
  .kpi-sub { font-size:13px; font-weight:700; }
  .up { color:var(--green); } .down { color:var(--red); } .flat { color:var(--muted); }
  .card { background:var(--card); border-radius:18px; padding:24px; margin-top:22px;
    box-shadow:0 18px 40px -26px rgba(2,6,23,.4); border:1px solid #eef0f6; }
  .card h2 { margin:0 0 4px; font-size:19px; font-weight:800; letter-spacing:-.3px; }
  .card p.lead { margin:0 0 16px; color:var(--muted); font-size:13.5px; }
  .two { display:grid; grid-template-columns:1fr 1fr; gap:22px; }
  table { width:100%; border-collapse:collapse; font-size:14px; }
  th,td { text-align:left; padding:11px 12px; border-bottom:1px solid #eef0f6; }
  th { font-size:11.5px; text-transform:uppercase; letter-spacing:.06em; color:var(--muted); }
  td.num,th.num { text-align:right; font-variant-numeric:tabular-nums; }
  td.metric { font-weight:700; } td.dev { font-weight:800; }
  .badge { padding:4px 10px; border-radius:999px; font-size:11.5px; font-weight:800; white-space:nowrap; }
  .badge.pass { background:#dcfce7; color:#15803d; } .badge.flag { background:#fef3c7; color:#b45309; }
  .lyr { padding:3px 9px; border-radius:7px; font-size:11px; font-weight:800; text-transform:uppercase; letter-spacing:.04em; }
  .lyr.bronze { background:#fef3c7; color:#92400e; } .lyr.silver { background:#e2e8f0; color:#334155; }
  .lyr.gold { background:#fae8c8; color:#a16207; }
  .chart { width:100%; height:auto; }
  .ax { fill:#94a3b8; font-size:11px; } .bl { fill:#475569; font-size:13px; font-weight:600; }
  .bv { fill:#0f172a; font-size:12.5px; font-weight:800; }
  .flow { display:flex; align-items:stretch; gap:0; overflow-x:auto; padding-bottom:8px; }
  .stage { min-width:150px; flex:1; border-radius:14px; padding:14px; border:1px solid #e7ebf3; background:#fbfcfe; }
  .stage.before { border-top:3px solid #f59e0b; } .stage.mid { border-top:3px solid #6366f1; }
  .stage.after { border-top:3px solid #22c55e; }
  .stage-h { font-weight:800; font-size:13px; letter-spacing:.02em; }
  .nodes { display:flex; flex-direction:column; gap:5px; margin:10px 0; }
  .node { font-size:11.5px; font-family:ui-monospace,SFMono-Regular,Menlo,monospace; background:#eef2ff;
    color:#3730a3; padding:4px 7px; border-radius:7px; word-break:break-all; }
  .stage.after .node { background:#ecfdf5; color:#065f46; }
  .stage-note { font-size:11px; color:var(--muted); line-height:1.4; }
  .arrow { display:flex; align-items:center; color:#94a3b8; font-size:22px; padding:0 6px; }
  .roi-grid { display:grid; grid-template-columns:repeat(3,1fr); gap:14px; margin:6px 0 14px; }
  .roi { background:#f8fafc; border:1px solid #eef0f6; border-radius:14px; padding:16px; }
  .roi.accent { background:linear-gradient(135deg,#eef2ff,#faf5ff); border-color:#ddd6fe; }
  .roi-n { font-size:24px; font-weight:800; letter-spacing:-.4px; }
  .roi-l { font-size:12px; color:var(--muted); font-weight:600; margin-top:3px; }
  code { background:#eef2ff; padding:1px 5px; border-radius:5px; font-size:12px; }
  a.tlink { color:#4f46e5; font-weight:800; text-decoration:none; border-bottom:1px dashed #c7d2fe; cursor:pointer; }
  a.tlink:hover { color:#3730a3; border-bottom-style:solid; }
  .modal-bg { display:none; position:fixed; inset:0; background:rgba(2,6,23,.55); z-index:50;
    padding:40px 16px; overflow-y:auto; }
  .modal-bg.open { display:block; }
  .modal { max-width:880px; margin:0 auto; background:#fff; border-radius:16px; padding:24px 24px 8px;
    box-shadow:0 30px 80px -20px rgba(2,6,23,.6); position:relative; }
  .modal h3 { margin:0 36px 4px 0; font-size:18px; font-weight:800; }
  .modal .msub { color:var(--muted); font-size:12.5px; margin:0 0 16px; }
  .modal-x { position:absolute; top:14px; right:16px; border:none; background:#f1f5f9; width:32px; height:32px;
    border-radius:9px; font-size:20px; line-height:1; cursor:pointer; color:#475569; }
  .modal-x:hover { background:#e2e8f0; }
  .tcase { border:1px solid #eef0f6; border-radius:12px; margin-bottom:14px; overflow:hidden; }
  .tcase-h { background:#f8fafc; padding:10px 14px; font-weight:700; font-size:13.5px; border-bottom:1px solid #eef0f6;
    font-family:ui-monospace,SFMono-Regular,Menlo,monospace; }
  .tcat { font-size:10.5px; font-weight:800; padding:2px 8px; border-radius:6px; margin-right:8px;
    background:#eef2ff; color:#4338ca; text-transform:uppercase; letter-spacing:.03em; }
  .tcat.singular { background:#fef3c7; color:#92400e; } .tcat.unit { background:#ecfdf5; color:#047857; }
  .modal pre { margin:0; padding:14px; background:#0b1020; color:#e2e8f0; font-size:12px; line-height:1.5;
    overflow-x:auto; font-family:ui-monospace,SFMono-Regular,Menlo,monospace; white-space:pre; }
  footer { color:var(--muted); font-size:12.5px; margin-top:28px; text-align:center; line-height:1.7; }
  .gates span { display:inline-block; margin:0 4px; padding:3px 9px; background:#e0e7ff; color:#4338ca;
    border-radius:7px; font-weight:700; font-size:11.5px; }
  @media (max-width:820px) { .grid { grid-template-columns:repeat(2,1fr); } .two { grid-template-columns:1fr; }
    .roi-grid { grid-template-columns:1fr 1fr; } }
"""

JS = """
  document.querySelectorAll('.tab').forEach(function(btn){
    btn.addEventListener('click', function(){
      document.querySelectorAll('.tab').forEach(function(b){ b.classList.remove('active'); });
      document.querySelectorAll('.panel').forEach(function(p){ p.classList.remove('active'); });
      btn.classList.add('active');
      var el = document.getElementById(btn.getAttribute('data-tab'));
      if (el) el.classList.add('active');
    });
  });
  document.querySelectorAll('.kpi-val[data-count]').forEach(function(el){
    var target = parseFloat(el.getAttribute('data-count')) || 0, t0 = null, dur = 1100;
    function tick(ts){ if(!t0) t0 = ts; var p = Math.min((ts-t0)/dur, 1);
      var v = Math.floor((1-Math.pow(1-p,3)) * target);
      el.textContent = v.toLocaleString(); if(p<1) requestAnimationFrame(tick); }
    requestAnimationFrame(tick);
  });
  // test-case drill-down: clicking a coverage number opens its test definitions
  var CAT_LABEL = {schema:'Schema tests', singular:'Singular tests', unit:'Unit tests', all:'All tests'};
  function esc(s){ return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }
  function ttdShow(model, cat){
    var d = TTD_TESTS[model]; if(!d) return;
    var items = cat==='all' ? d.schema.concat(d.singular, d.unit) : (d[cat]||[]);
    document.getElementById('tmodal-title').textContent = model;
    document.getElementById('tmodal-sub').textContent = CAT_LABEL[cat] + ' · ' + items.length + ' test' + (items.length===1?'':'s');
    document.getElementById('tmodal-body').innerHTML = items.map(function(it){
      var kc = it.kind.replace(/[^a-z]/gi,'').toLowerCase();
      return '<div class="tcase"><div class="tcase-h"><span class="tcat '+kc+'">'+esc(it.kind)+'</span>'+esc(it.name)+'</div><pre>'+esc(it.code)+'</pre></div>';
    }).join('') || '<p class="msub">No tests in this category.</p>';
    document.getElementById('tmodal').classList.add('open');
  }
  document.querySelectorAll('a.tlink').forEach(function(a){
    a.addEventListener('click', function(e){ e.preventDefault(); ttdShow(a.getAttribute('data-m'), a.getAttribute('data-c')); });
  });
  function ttdClose(){ document.getElementById('tmodal').classList.remove('open'); }
  var mx = document.querySelector('.modal-x'); if (mx) mx.addEventListener('click', ttdClose);
  var mb = document.getElementById('tmodal');
  if (mb) mb.addEventListener('click', function(e){ if(e.target.id==='tmodal') ttdClose(); });
  document.addEventListener('keydown', function(e){ if(e.key==='Escape') ttdClose(); });
"""


# --------------------------------------------------------------------------- #
# document assembly
# --------------------------------------------------------------------------- #
def build_html(product, gen_ts, src, kpis, region_series, month_series,
               cov_kpis, cov_rows, flow, kinds_seen, wf_stats,
               tel, model_id, labor_rate, test_details) -> str:
    kpi_html = _kpi_html(kpis)
    cov_kpi_html = _kpi_html(cov_kpis)
    cov_table = _coverage_rows_html(cov_rows)
    flow_html = _flow_html(flow)
    workflow_html = _build_workflow_html(wf_stats)
    tk_kpis, tk_models, tk_steps, tk_roi = build_tokenomics(tel, model_id, labor_rate)
    model_name = MODEL_LABEL.get(model_id, model_id)
    badges = "".join(f"<span>{escape(k)}</span>" for k in sorted(kinds_seen))
    tests_json = json.dumps(test_details, separators=(",", ":")).replace("</", "<\\/")
    total_models = len(cov_rows)
    covered = sum(1 for r in cov_rows if r["covered"])

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>{escape(product)} -- TTD Executive Dashboard</title>
<style>{CSS}</style></head>
<body>
  <header class="hero"><div class="wrap">
    <div class="eyebrow">Test-Then-Deploy &middot; Executive Summary</div>
    <h1>{escape(product)}</h1>
    <div class="sub">A medallion dbt project on Snowflake where every model is gated by tests before it
      ships. Bronze &rarr; silver &rarr; gold, with a coverage gate that blocks any untested model.</div>
    <div class="pill"><span class="dot"></span> COVERAGE GATE PASSED &middot; {covered}/{total_models} models tested &middot; live gold data</div>
  </div></header>

  <div class="wrap">
    <div class="tabs">
      <button class="tab active" data-tab="exec">Executive Summary</button>
      <button class="tab" data-tab="coverage">Test Coverage</button>
      <button class="tab" data-tab="lineage">Lineage</button>
      <button class="tab" data-tab="tokens">Tokenomics</button>
      <button class="tab" data-tab="workflow">Workflow</button>
    </div>

    <!-- TAB 1: EXECUTIVE SUMMARY -->
    <section class="panel active" id="exec">
      <div class="grid">{kpi_html}</div>
      <div class="two">
        <div class="card"><h2>Net revenue by region</h2>
          <p class="lead">Sum of net revenue across orders, by customer region (live gold).</p>{svg_bars(region_series, fmt=money_compact)}</div>
        <div class="card"><h2>Monthly net revenue</h2>
          <p class="lead">Net revenue by order month (filtered to the demo window).</p>{svg_area(month_series)}</div>
      </div>
    </section>

    <!-- TAB 2: TEST COVERAGE -->
    <section class="panel" id="coverage">
      <div class="grid">{cov_kpi_html}</div>
      <div class="card">
        <h2>Coverage scorecard -- every model, every gate</h2>
        <p class="lead">Functional (schema), singular, and characterization unit tests attached to each model.
          A model with zero tests fails the coverage gate and cannot deploy. <b>Click any number to view the
          test cases written.</b> Source: dbt manifest.</p>
        <table>
          <thead><tr><th>Model</th><th>Layer</th><th>Materialized</th>
            <th class="num">Schema</th><th class="num">Singular</th><th class="num">Unit</th>
            <th class="num">Total</th><th>Gate</th></tr></thead>
          <tbody>{cov_table}</tbody>
        </table>
      </div>
    </section>

    <!-- TAB 3: LINEAGE -->
    <section class="panel" id="lineage">
      <div class="card">
        <h2>Medallion lineage</h2>
        <p class="lead">TPC-H sample data flows through bronze (raw views) and silver (conformed views)
          into gold facts and dimensions. Built live from the dbt manifest.</p>
        {flow_html}
      </div>
    </section>

    <!-- TAB 4: TOKENOMICS -->
    <section class="panel" id="tokens">
      <div class="grid">{tk_kpis}</div>
      <div class="card">
        <h2>Return on investment</h2>
        <p class="lead">Cost of the AI-assisted build of this TTD project vs the manual analyst baseline it replaces.</p>
        {tk_roi}
      </div>
      <div class="two">
        <div class="card"><h2>Model &amp; pricing</h2>
          <p class="lead">Orchestrator: <b>{escape(model_name)}</b>. Per-1M-token input/output rates.</p>
          <table><thead><tr><th>Model</th><th>Role</th><th class="num">$/1M in&middot;out</th></tr></thead>
            <tbody>{tk_models}</tbody></table></div>
        <div class="card"><h2>Per-step token &amp; cost</h2>
          <p class="lead">Estimated tokens and cost per build step.</p>
          <table><thead><tr><th class="num">#</th><th>Step</th><th class="num">In</th><th class="num">Out</th><th class="num">Cost</th></tr></thead>
            <tbody>{tk_steps}</tbody></table></div>
      </div>
    </section>

    <!-- TAB 5: WORKFLOW -->
    <section class="panel" id="workflow">
      {workflow_html}
    </section>

    <footer>
      <div class="gates">{badges}</div>
      <div>Source: {escape(src)} &middot; generated {escape(gen_ts)} &middot; self-contained &mdash; no server / no internet required</div>
    </footer>
  </div>

  <!-- test-case drill-down modal -->
  <div class="modal-bg" id="tmodal">
    <div class="modal">
      <button class="modal-x" aria-label="close">&times;</button>
      <h3 id="tmodal-title"></h3>
      <p class="msub" id="tmodal-sub"></p>
      <div id="tmodal-body"></div>
    </div>
  </div>

  <script>const TTD_TESTS = {tests_json};</script>
  <script>{JS}</script>
</body></html>"""


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="ttd dashboard")
    ap.add_argument("--product", default="TTD Medallion")
    ap.add_argument("--database", default="DB01")
    ap.add_argument("--labor-rate", type=float, default=100.0)
    a = ap.parse_args(argv)

    ART.mkdir(exist_ok=True)
    manifest = load_manifest()

    # ---- coverage + lineage from the manifest ----
    cov_rows, kinds_seen = compute_coverage(manifest)
    total_models = len(cov_rows)
    covered = sum(1 for r in cov_rows if r["covered"])
    total_tests = sum(r["total"] for r in cov_rows)
    unit_tests = sum(r["unit"] for r in cov_rows)
    cov_pct = round(covered / total_models * 100) if total_models else 0

    cov_kpis = [
        {"label": "Models", "value": str(total_models), "data": total_models, "sub": "bronze + silver + gold"},
        {"label": "Models tested", "value": str(covered), "data": covered,
         "sub": f"{cov_pct}% coverage", "cls": "up" if covered == total_models else "down"},
        {"label": "Total tests", "value": str(total_tests), "data": total_tests, "sub": "schema + singular + unit"},
        {"label": "Unit tests", "value": str(unit_tests), "data": unit_tests, "sub": "characterization"},
    ]
    flow = lineage_stages(manifest, cov_rows)
    model_uids = {r["uid"]: r["name"] for r in cov_rows}
    test_details = build_test_details(manifest, model_uids)

    # ---- live business KPIs from the gold layer ----
    fct = relation_of(manifest, "fct_orders")
    dim = relation_of(manifest, "dim_customers")
    hvo = relation_of(manifest, "fct_high_value_orders")
    if not (fct and dim and hvo):
        sys.exit("could not resolve gold relations from manifest -- build the gold models first.")

    tot = q1(f"select count(*) as orders, sum(net_revenue) as revenue, "
             f"sum(net_revenue_with_tax) as revenue_tax from {fct}")
    cust = q1(f"select count(*) as customers from {dim}")
    hv = q1(f"select count(*) as hv_orders, coalesce(sum(revenue),0) as hv_revenue from {hvo}")
    region_rows = show(f"select region_name, sum(net_revenue) as revenue, count(*) as orders "
                       f"from {fct} group by region_name order by revenue desc")
    month_rows = show(f"select order_month, sum(net_revenue) as revenue "
                      f"from {fct} group by order_month order by order_month")

    region_series = [(r.get("region_name") or "-", num(r.get("revenue"))) for r in region_rows]
    month_series = [(str(r.get("order_month"))[:7], num(r.get("revenue"))) for r in month_rows]

    kpis = [
        {"label": "Total orders", "value": fmt_int(tot.get("orders")), "data": num(tot.get("orders")),
         "sub": "gold · fct_orders"},
        {"label": "Net revenue", "value": money_compact(tot.get("revenue")),
         "sub": f"{money_compact(tot.get('revenue_tax'))} with tax", "cls": "up"},
        {"label": "Customers", "value": fmt_int(cust.get("customers")), "data": num(cust.get("customers")),
         "sub": "gold · dim_customers"},
        {"label": "High-value orders", "value": fmt_int(hv.get("hv_orders")), "data": num(hv.get("hv_orders")),
         "sub": f"{money_compact(hv.get('hv_revenue'))} · net >= $50k"},
    ]

    wf_stats = [
        (f"{covered}/{total_models}", "models gated by tests"),
        (fmt_int(total_tests), "tests in the suite"),
        (fmt_int(unit_tests), "characterization unit tests"),
        ("PASS" if covered == total_models else "FAIL", "coverage gate"),
    ]

    # ---- tokenomics (editable estimates from artifacts/ttd_telemetry.json) ----
    tel = load_telemetry()
    model_id = _orchestrator_model(tel)

    # ---- write the dashboard ----
    src = f"{a.database}.TTD_GOLD (live) + dbt manifest"
    gen_ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    html = build_html(a.product, gen_ts, src, kpis, region_series, month_series,
                      cov_kpis, cov_rows, flow, kinds_seen, wf_stats,
                      tel, model_id, a.labor_rate, test_details)
    out = ART / "TTD_Exec_Dashboard.html"
    out.write_text(html, encoding="utf-8")

    # ---- write the supporting artifacts library ----
    _write_csv(ART / "gold_orders_by_region.csv", ["region_name", "net_revenue", "orders"],
               [(r.get("region_name"), r.get("revenue"), r.get("orders")) for r in region_rows])
    _write_csv(ART / "gold_orders_by_month.csv", ["order_month", "net_revenue"],
               [(r.get("order_month"), r.get("revenue")) for r in month_rows])
    # top-1000 sample (the full set can be 100k+ rows); labelled as a sample in README
    hv_rows = show(f"select order_id, customer, region, order_date, revenue, revenue_with_tax "
                   f"from {hvo} order by revenue desc", limit=1000)
    _write_csv(ART / "high_value_orders.csv",
               ["order_id", "customer", "region", "order_date", "revenue", "revenue_with_tax"],
               [(r.get("order_id"), r.get("customer"), r.get("region"), r.get("order_date"),
                 r.get("revenue"), r.get("revenue_with_tax")) for r in hv_rows])

    _write_csv(ART / "coverage_report.csv",
               ["model", "layer", "materialized", "schema_tests", "singular_tests", "unit_tests", "total", "gate"],
               [(r["name"], r["layer"], r["materialized"], r["data"], r["singular"], r["unit"],
                 r["total"], "PASS" if r["covered"] else "UNTESTED") for r in cov_rows])
    _write_csv(ART / "model_inventory.csv", ["model", "layer", "materialized", "total_tests"],
               [(r["name"], r["layer"], r["materialized"], r["total"]) for r in cov_rows])

    cov_md = ["# TTD Coverage Report", "",
              f"_Generated {gen_ts}. Source: dbt manifest ({manifest['metadata'].get('dbt_version')})._", "",
              f"**{covered}/{total_models} models tested ({cov_pct}%) · {total_tests} tests "
              f"({unit_tests} unit) · coverage gate: {'PASS' if covered == total_models else 'FAIL'}**", "",
              "| Model | Layer | Materialized | Schema | Singular | Unit | Total | Gate |",
              "|---|---|---|--:|--:|--:|--:|---|"]
    for r in cov_rows:
        cov_md.append(f"| {r['name']} | {r['layer']} | {r['materialized']} | {r['data']} | "
                      f"{r['singular']} | {r['unit']} | {r['total']} | "
                      f"{'PASS' if r['covered'] else '**UNTESTED**'} |")
    (ART / "coverage_report.md").write_text("\n".join(cov_md) + "\n", encoding="utf-8")

    telemetry = {
        "project": manifest["metadata"]["project_name"],
        "generated_utc": gen_ts,
        "dbt_version": manifest["metadata"].get("dbt_version"),
        "source": src,
        "coverage": {"models": total_models, "models_tested": covered, "coverage_pct": cov_pct,
                     "total_tests": total_tests, "unit_tests": unit_tests,
                     "gate": "PASS" if covered == total_models else "FAIL",
                     "test_kinds": sorted(kinds_seen)},
        "gold_kpis": {"total_orders": int(num(tot.get("orders"))),
                      "net_revenue": round(num(tot.get("revenue")), 2),
                      "net_revenue_with_tax": round(num(tot.get("revenue_tax")), 2),
                      "customers": int(num(cust.get("customers"))),
                      "high_value_orders": int(num(hv.get("hv_orders"))),
                      "high_value_revenue": round(num(hv.get("hv_revenue")), 2)},
        "models": [{"model": r["name"], "layer": r["layer"], "materialized": r["materialized"],
                    "schema_tests": r["data"], "singular_tests": r["singular"],
                    "unit_tests": r["unit"], "gate": "PASS" if r["covered"] else "UNTESTED"}
                   for r in cov_rows],
    }
    _tok = tel.get("totals_est", {})
    _in_rate, _out_rate = PRICING.get(model_id, PRICING["claude-opus-4-8"])
    _ai_cost = num(_tok.get("tokens_input_est")) / 1e6 * _in_rate + \
        num(_tok.get("tokens_output_est")) / 1e6 * _out_rate
    telemetry["tokenomics_est"] = {
        "model": model_id,
        "tokens_input_est": int(num(_tok.get("tokens_input_est"))),
        "tokens_output_est": int(num(_tok.get("tokens_output_est"))),
        "wall_clock_minutes": _tok.get("wall_clock_minutes"),
        "ai_run_cost_usd": round(_ai_cost, 2),
        "source": "artifacts/ttd_telemetry.json (estimates)",
    }
    (ART / "run_telemetry.json").write_text(json.dumps(telemetry, indent=2), encoding="utf-8")

    readme = f"""# TTD artifacts

Evidence library generated by `python ttd.py dashboard`. Mirrors the PI artifacts
convention: a self-contained executive dashboard plus the data + reports behind it.

| File | What it is |
|---|---|
| `TTD_Exec_Dashboard.html` | Self-contained executive dashboard (4 tabs: Executive Summary / Test Coverage / Lineage / Workflow). Opens offline in any browser. |
| `coverage_report.md` / `.csv` | Per-model test coverage + coverage-gate status. |
| `model_inventory.csv` | Every model with its layer, materialization, and test count. |
| `gold_orders_by_region.csv` | Net revenue + order count by region (Exec Summary chart data). |
| `gold_orders_by_month.csv` | Net revenue by order month (Exec Summary trend data). |
| `high_value_orders.csv` | Top 1,000 `fct_high_value_orders` by revenue (net revenue >= $50k); a sample, not the full set. |
| `run_telemetry.json` | Machine-readable summary: coverage, gold KPIs, per-model test breakdown, tokenomics. |
| `ttd_telemetry.json` | **Editable** tokenomics input (model, per-step token estimates, wall-clock) for the Tokenomics tab. Edit with actuals. |

Regenerate any time with `python ttd.py dashboard`. Coverage + lineage come from the
dbt manifest; the business KPIs are queried live from `{a.database}.TTD_GOLD`.
"""
    (ART / "README.md").write_text(readme, encoding="utf-8")

    # ---- console summary ----
    print("TTD dashboard")
    print("-" * 13)
    print(f"  coverage    : {covered}/{total_models} models tested ({cov_pct}%) · "
          f"{total_tests} tests ({unit_tests} unit) · gate {'PASS' if covered == total_models else 'FAIL'}")
    print(f"  gold KPIs   : {fmt_int(tot.get('orders'))} orders · {money_compact(tot.get('revenue'))} net revenue · "
          f"{fmt_int(cust.get('customers'))} customers · {fmt_int(hv.get('hv_orders'))} high-value")
    print(f"  tokenomics  : {model_id} · {fmt_int(_tok.get('tokens_input_est'))} in / "
          f"{fmt_int(_tok.get('tokens_output_est'))} out -> {money2(_ai_cost)} (estimates)")
    print(f"  artifacts   : {ART}")
    print(f"\nOutput: {out}  (open in any browser, fully offline)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

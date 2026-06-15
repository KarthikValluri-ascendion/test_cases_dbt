# Test-Then-Deploy — Enterprise Standard

- **Every dbt model ships with at least one test** (schema, singular, or unit). No exceptions
  without an explicit `exempt_prefixes` entry, used only to grandfather legacy models during
  rollout and ratcheted down over time.
- **The coverage gate runs on every `dbt run` / `dbt build`** via `on-run-start`
  (`ttd_enforce_coverage`) and aborts the run on any uncovered model. The real enforcement
  point in an org is CI/CD — wire the same `dbt build` into the PR pipeline.
- **Functional test stubs are auto-generated pre-build** (`not_null` / `unique`); they make the
  compliant path the easy path. Review and tighten them, then fold into the real `_*__models.yml`.
- **Characterization unit tests are auto-generated post-build** by sampling real rows and
  capturing the model's actual output. They catch *unintended behaviour drift*, not correctness
  against a spec — they MUST be human-reviewed before they are trusted. If the model is currently
  wrong, the generated test enshrines the wrong answer.
- **Multi-table join models** may fall back to a commented skeleton (independent samples don't
  share join keys) — give those hand-written unit tests.

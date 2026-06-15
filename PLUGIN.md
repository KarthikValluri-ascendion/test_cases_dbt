# TTD Claude Code plugin

This repo (`test_cases_dbt`) hosts the **`ttd`** Claude Code plugin (under `ttd-plugin/`)
plus the demo dbt medallion project.

The plugin is published through the shared **`claude-enterprise-standards`** marketplace
(hosted in the `zoom-pi-ftl-migration` repo), which references this repo's `ttd-plugin/`
via a `git-subdir` source — so `ttd` installs alongside `pi-ftl` from one enterprise marketplace.

## Layout

```
ttd-plugin/
├── .claude-plugin/plugin.json      # plugin manifest (name: ttd)
├── skills/                         # the /ttd:* commands (auto-discovered)
│   ├── enforce/SKILL.md            # /ttd:enforce
│   ├── scaffold/SKILL.md           # /ttd:scaffold
│   ├── gen-unit-tests/SKILL.md     # /ttd:gen-unit-tests
│   ├── build/SKILL.md              # /ttd:build
│   └── demo-reset/SKILL.md         # /ttd:demo-reset
├── assets/                         # canonical hook artifacts (macros + python + config + standard)
└── docs/README.md
```

## Install & use

The `claude-enterprise-standards` marketplace is already registered (it hosts `pi-ftl`).
Once the marketplace entry for `ttd` is merged:

```text
/plugin install ttd@claude-enterprise-standards
/ttd:demo-reset      # RED
/ttd:build           # GREEN — scaffolds tests + builds + generates & runs unit tests
```

If the marketplace isn't registered on a machine yet:
```text
/plugin marketplace add KarthikValluri-ascendion/zoom-pi-ftl-migration
```

## How the marketplace references this plugin

The `ttd` entry in the enterprise `marketplace.json` (in the PI repo) is a cross-repo source:
```json
{
  "name": "ttd",
  "source": { "source": "git-subdir", "url": "KarthikValluri-ascendion/test_cases_dbt", "path": "ttd-plugin", "ref": "main" },
  "description": "Test-Then-Deploy for dbt + Snowflake medallion projects."
}
```
So the plugin code stays here in `test_cases_dbt`, while the install name remains
`ttd@claude-enterprise-standards`.

# TTD Claude Code plugin + marketplace

This repo (`test_cases_dbt`) doubles as the **`claude-enterprise-standards`** Claude Code plugin
marketplace and hosts the **`ttd`** plugin.

## Layout

```
.claude-plugin/marketplace.json     # marketplace: claude-enterprise-standards -> lists the ttd plugin
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

## Use it

```text
/plugin marketplace add KarthikValluri-ascendion/test_cases_dbt
/plugin install ttd@claude-enterprise-standards
/ttd:demo-reset      # RED
/ttd:build           # GREEN — scaffolds tests + builds + generates & runs unit tests
```

## Local testing (before pushing to GitHub)

```text
/plugin marketplace add ./        # add this repo as a local marketplace
/plugin install ttd@claude-enterprise-standards
/ttd:enforce
```

## Adding more enterprise plugins

`marketplace.json` has a `plugins[]` array — add another entry (e.g. `pi-ftl` pointing at its
repo) so it installs from the same `@claude-enterprise-standards` marketplace.

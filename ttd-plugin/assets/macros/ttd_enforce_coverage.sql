{#
    TTD coverage gate.

    Runs as an on-run-start hook. Walks the parsed graph, builds the set of
    models that have at least one attached test (generic schema test, singular
    test, OR native unit test), and aborts the run if any in-scope model has
    none.

    This is the "enforce" half of TTD: no untested model is allowed to build.

    Controls (set in dbt_project.yml `vars` or via --vars):
      ttd_enforce: true|false          -- master switch
      ttd_exempt_prefixes: ['brz_']    -- model name prefixes that are exempt
#}
{% macro ttd_enforce_coverage() %}
    {#-- Only meaningful at execute time, when the graph is populated. --#}
    {% if not execute %}{{ return('') }}{% endif %}
    {% if not var('ttd_enforce', true) %}
        {{ log("TTD: enforcement disabled (ttd_enforce=false).", info=true) }}
        {{ return('') }}
    {% endif %}

    {% set exempt_prefixes = var('ttd_exempt_prefixes', []) %}

    {#-- 1. Collect every model unique_id that some test depends on. --#}
    {% set covered = [] %}
    {% for node in graph.nodes.values() %}
        {% if node.resource_type in ['test', 'unit_test'] %}
            {% for dep in node.depends_on.nodes %}
                {% if dep.startswith('model.') and dep not in covered %}
                    {% do covered.append(dep) %}
                {% endif %}
            {% endfor %}
        {% endif %}
    {% endfor %}

    {#-- 2. Find in-scope models with no coverage. --#}
    {% set uncovered = [] %}
    {% for node in graph.nodes.values() %}
        {% if node.resource_type == 'model' %}
            {% set is_exempt = false %}
            {% for p in exempt_prefixes %}
                {% if node.name.startswith(p) %}{% set is_exempt = true %}{% endif %}
            {% endfor %}
            {% if not is_exempt and node.unique_id not in covered %}
                {% do uncovered.append(node.name) %}
            {% endif %}
        {% endif %}
    {% endfor %}

    {#-- 3. Pass or abort. --#}
    {% if uncovered | length > 0 %}
        {% set msg %}

TTD COVERAGE GATE FAILED
------------------------
The following {{ uncovered | length }} model(s) have NO tests (schema, singular, or unit):

  {% for m in uncovered %}- {{ m }}
  {% endfor %}
Every model must ship with at least one test before it can build.
Generate stubs with:  python ttd.py scaffold
Or exempt a prefix in dbt_project.yml (vars: ttd_exempt_prefixes).
Or bypass for one run:  dbt build --vars 'ttd_enforce: false'
        {% endset %}
        {{ exceptions.raise_compiler_error(msg) }}
    {% else %}
        {{ log("TTD: coverage gate passed - all in-scope models have tests.", info=true) }}
    {% endif %}
    {{ return('') }}
{% endmacro %}

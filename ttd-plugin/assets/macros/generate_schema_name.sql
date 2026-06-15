{#
    Namespaced schema generation so this project's BRONZE/SILVER/GOLD layers
    never collide with the pre-existing BRONZE/SILVER/GOLD schemas in DB01.

    With a +schema of "bronze" and target schema "DB01_KV01" this yields
    schema "TTD_BRONZE" (not "DB01_KV01_bronze"). The TTD_ prefix keeps the
    demo self-contained and easy to drop.
#}
{% macro generate_schema_name(custom_schema_name, node) -%}
    {%- if custom_schema_name is none -%}
        {{ target.schema }}
    {%- else -%}
        TTD_{{ custom_schema_name | trim | upper }}
    {%- endif -%}
{%- endmacro %}

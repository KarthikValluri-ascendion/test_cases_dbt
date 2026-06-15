-- Bronze: raw 1:1 passthrough of TPC-H nation.
select
    n_nationkey as nation_key,
    n_name      as nation_name,
    n_regionkey as region_key,
    n_comment   as comment
from {{ source('tpch', 'nation') }}

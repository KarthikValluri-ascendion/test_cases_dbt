-- Bronze: raw 1:1 passthrough of TPC-H customer. No business logic, only renaming.
select
    c_custkey    as customer_key,
    c_name       as customer_name,
    c_address    as address,
    c_nationkey  as nation_key,
    c_phone      as phone,
    c_acctbal    as account_balance,
    c_mktsegment as market_segment,
    c_comment    as comment
from {{ source('tpch', 'customer') }}

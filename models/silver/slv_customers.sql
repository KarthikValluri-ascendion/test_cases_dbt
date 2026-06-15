-- Silver: conformed customer enriched with nation + region geography.
with customer as (
    select * from {{ ref('brz_customer') }}
),
nation as (
    select * from {{ ref('brz_nation') }}
),
region as (
    select * from {{ ref('brz_region') }}
)
select
    c.customer_key,
    c.customer_name,
    c.market_segment,
    c.account_balance,
    -- negative balances are valid (credit owed); flag them rather than drop
    (c.account_balance < 0)            as has_negative_balance,
    c.nation_key,
    n.nation_name,
    r.region_key,
    r.region_name
from customer c
left join nation n on c.nation_key = n.nation_key
left join region r on n.region_key = r.region_key

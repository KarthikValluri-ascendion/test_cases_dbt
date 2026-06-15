-- Gold: customer dimension, business-facing. One row per customer.
with customers as (
    select * from {{ ref('slv_customers') }}
)
select
    customer_key,
    customer_name,
    market_segment,
    account_balance,
    has_negative_balance,
    nation_name,
    region_name
from customers

{{ config(materialized='view') }}
-- DEMO FIXTURE: high-value orders for sales prioritisation.
-- Intentionally ships WITHOUT tests to demonstrate the TTD coverage gate.
-- `python ttd.py demo-reset` removes its generated stub to return to the
-- "untested" starting state; `python ttd.py build` scaffolds + builds it green.
select
    order_key            as order_id,
    customer_name        as customer,
    region_name          as region,
    order_date           as order_date,
    net_revenue          as revenue,
    net_revenue_with_tax as revenue_with_tax
from {{ ref('fct_orders') }}
where net_revenue >= 50000

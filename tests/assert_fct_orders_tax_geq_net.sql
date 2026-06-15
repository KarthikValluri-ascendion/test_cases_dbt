-- Functional/singular test: tax-inclusive revenue can never be LESS than
-- the pre-tax revenue. Returns offending rows; the test passes when empty.
select
    order_key,
    net_revenue,
    net_revenue_with_tax
from {{ ref('fct_orders') }}
where net_revenue_with_tax < net_revenue

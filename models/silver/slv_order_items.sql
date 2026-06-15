-- Silver: line items for in-scope orders, with revenue math made explicit.
-- net_amount = extended_price * (1 - discount), then tax applied on top.
with line_items as (
    select * from {{ ref('brz_lineitem') }}
),
orders as (
    select order_key from {{ ref('slv_orders') }}
)
select
    li.order_key,
    li.line_number,
    li.part_key,
    li.quantity,
    li.extended_price,
    li.discount,
    li.tax,
    round(li.extended_price * (1 - li.discount), 2)              as net_amount,
    round(li.extended_price * (1 - li.discount) * (1 + li.tax), 2) as net_amount_with_tax,
    li.return_flag,
    li.ship_mode,
    li.ship_date
from line_items li
-- inner join restricts line items to the date-bounded order set
inner join orders o on li.order_key = o.order_key

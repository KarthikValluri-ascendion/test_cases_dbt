-- Gold: order fact at one row per order. Order header + rolled-up line revenue
-- + customer geography for slicing.
with orders as (
    select * from {{ ref('slv_orders') }}
),
order_items as (
    select
        order_key,
        count(*)                  as line_item_count,
        sum(quantity)             as total_quantity,
        sum(net_amount)           as net_revenue,
        sum(net_amount_with_tax)  as net_revenue_with_tax
    from {{ ref('slv_order_items') }}
    group by order_key
),
customers as (
    select customer_key, customer_name, market_segment, nation_name, region_name
    from {{ ref('dim_customers') }}
)
select
    o.order_key,
    o.customer_key,
    c.customer_name,
    c.market_segment,
    c.nation_name,
    c.region_name,
    o.order_status_label,
    o.order_date,
    o.order_month,
    o.order_year,
    o.order_priority,
    o.total_price,
    coalesce(oi.line_item_count, 0)        as line_item_count,
    coalesce(oi.total_quantity, 0)         as total_quantity,
    coalesce(oi.net_revenue, 0)            as net_revenue,
    coalesce(oi.net_revenue_with_tax, 0)   as net_revenue_with_tax
from orders o
left join order_items oi on o.order_key = oi.order_key
left join customers c on o.customer_key = c.customer_key

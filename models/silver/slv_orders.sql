-- Silver: cleaned orders, bounded by var('start_date') to keep gold tables light.
with orders as (
    select * from {{ ref('brz_orders') }}
    where order_date >= '{{ var("start_date", "1998-01-01") }}'
)
select
    order_key,
    customer_key,
    order_status,
    -- normalize the single-char status code into a readable label
    case order_status
        when 'O' then 'open'
        when 'F' then 'fulfilled'
        when 'P' then 'partial'
        else 'unknown'
    end                                as order_status_label,
    total_price,
    order_date,
    date_trunc('month', order_date)    as order_month,
    extract(year from order_date)      as order_year,
    order_priority
from orders

-- Singular test: every SOLD listing must have a sale price above zero.
-- dbt runs this query; the test FAILS if it returns any rows.

select
    sale_id,
    vehicle_id,
    sale_price
from {{ ref('stg_auction_sales') }}
where is_sold
  and (sale_price is null or sale_price <= 0)

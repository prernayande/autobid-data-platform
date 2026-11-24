-- Mart: one row per damage type.
-- Answers: how much value does a car keep after damage, and which damage types sell best?
-- Plain SQL so it runs on both Snowflake and BigQuery.

with sales as (

    select * from {{ ref('stg_auction_sales') }}

),

vehicles as (

    select * from {{ ref('stg_vehicles') }}

),

-- each listing, with its car's MSRP and (if sold) the share of MSRP it sold for
listings as (

    select
        sales.damage_type,
        sales.is_sold,
        sales.sale_price,
        vehicles.msrp,
        case
            when sales.is_sold then sales.sale_price * 1.0 / vehicles.msrp
        end as value_retained        -- e.g. 0.12 = sold for 12% of MSRP; NULL if not sold

    from sales
    -- inner join: a listing for an unknown car has no MSRP, so it can't be priced.
    -- The relationships test (Step 8) fails loudly if that ever happens.
    inner join vehicles
        on sales.vehicle_id = vehicles.vehicle_id

),

final as (

    select
        damage_type,

        -- how well it sells
        count(*)                                                    as lots_listed,
        sum(case when is_sold then 1 else 0 end)                    as lots_sold,
        round(100.0 * sum(case when is_sold then 1 else 0 end)
              / count(*), 1)                                        as sell_through_pct,

        -- what it sells for (sold lots only: avg() skips NULLs)
        round(avg(sale_price), 0)                                   as avg_sale_price,
        round(avg(case when is_sold then msrp end), 0)              as avg_msrp,

        -- average of each car's own sale_price / msrp, so a $300k car counts the same as a $20k car
        round(100 * avg(value_retained), 1)                         as avg_value_retained_pct

    from listings
    group by damage_type

)

select * from final

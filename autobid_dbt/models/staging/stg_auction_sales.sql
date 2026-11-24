-- Staging: one row per auction listing, cleaned up from RAW.AUCTION_SALES.
-- Only renames, type casts and trimming. No business logic, no filtering:
-- bad rows are kept here on purpose so dbt tests can find and report them.
-- Plain SQL so it runs on both Snowflake and BigQuery.

with source as (

    select * from {{ source('raw', 'auction_sales') }}

),

cleaned as (

    select
        -- ids
        cast(sale_id as integer)                    as sale_id,
        cast(vehicle_id as integer)                 as vehicle_id,
        cast(lot_number as integer)                 as lot_number,

        -- what was sold, and where
        trim(damage_type)                           as damage_type,
        trim(title_type)                            as title_type,
        upper(trim(yard_state))                     as yard_state,
        cast(sale_date as date)                     as sale_date,

        -- auction result
        cast(bid_count as integer)                  as bid_count,
        cast(sale_price as integer)                 as sale_price,   -- NULL when not sold
        lower(trim(is_sold)) = 'true'               as is_sold,      -- text 'True'/'False' -> boolean

        -- audit
        _source_file                                as source_file,
        _loaded_at                                  as loaded_at

    from source

)

select * from cleaned

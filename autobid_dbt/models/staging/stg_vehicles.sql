-- Staging: one row per car, cleaned up from RAW.VEHICLES.
-- Only renames, type casts and trimming. No business logic, no filtering.
-- Plain SQL so it runs on both Snowflake and BigQuery.

with source as (

    select * from {{ source('raw', 'vehicles') }}

),

cleaned as (

    select
        -- ids
        cast(vehicle_id as integer)                 as vehicle_id,
        trim(vin)                                   as vin,

        -- car description
        trim(make)                                  as make,
        trim(model)                                 as model,
        cast(year as integer)                       as model_year,
        trim(vehicle_size)                          as vehicle_size,
        trim(vehicle_style)                         as vehicle_style,
        nullif(trim(market_category), 'N/A')        as market_category,   -- 'N/A' means no value

        -- engine and drivetrain
        trim(engine_fuel_type)                      as engine_fuel_type,
        cast(engine_hp as integer)                  as engine_hp,
        cast(engine_cylinders as integer)           as engine_cylinders,
        trim(transmission_type)                     as transmission_type,
        trim(driven_wheels)                         as driven_wheels,
        cast(number_of_doors as integer)            as number_of_doors,
        cast(highway_mpg as integer)                as highway_mpg,
        cast(city_mpg as integer)                   as city_mpg,

        -- price and popularity
        cast(msrp as integer)                       as msrp_usd,  -- DEMO: rename without updating the mart
        cast(popularity as integer)                 as popularity,

        -- audit
        _source_file                                as source_file,
        _loaded_at                                  as loaded_at

    from source

)

select * from cleaned

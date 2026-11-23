-- =============================================================================
-- AutoBid Data Platform: one-time Snowflake setup
--
-- Who runs this: a human admin (me), by hand, in the Snowsight web UI.
-- Why ACCOUNTADMIN: only an admin can create warehouses, resource monitors,
--   roles and users. Code (load script, dbt, CI) NEVER uses ACCOUNTADMIN;
--   it logs in as DBT_SVC with the limited role AUTOBID_ROLE.
-- Safe to re-run: every statement uses IF NOT EXISTS or only sets a value.
-- =============================================================================

USE ROLE ACCOUNTADMIN;

-- -----------------------------------------------------------------------------
-- 1. Warehouse = the compute that runs queries. Billed only while running.
--    X-Small is the smallest size. It turns off after 60 idle seconds and
--    turns back on by itself when a query arrives.
-- -----------------------------------------------------------------------------
CREATE WAREHOUSE IF NOT EXISTS AUTOBID_WH
  WAREHOUSE_SIZE      = 'XSMALL'
  AUTO_SUSPEND        = 60
  AUTO_RESUME         = TRUE
  INITIALLY_SUSPENDED = TRUE
  COMMENT = 'AutoBid project compute';

-- -----------------------------------------------------------------------------
-- 2. Resource monitor = a spending limit. After 20 credits in a month,
--    Snowflake suspends the warehouse, so a mistake can't burn the trial.
-- -----------------------------------------------------------------------------
CREATE RESOURCE MONITOR IF NOT EXISTS AUTOBID_MONITOR
  WITH CREDIT_QUOTA    = 20
       FREQUENCY       = MONTHLY
       START_TIMESTAMP = IMMEDIATELY
  TRIGGERS ON 100 PERCENT DO SUSPEND;

ALTER WAREHOUSE AUTOBID_WH SET RESOURCE_MONITOR = AUTOBID_MONITOR;

-- -----------------------------------------------------------------------------
-- 3. Database and schemas
--    RAW       = data loaded as-is from the CSV files
--    ANALYTICS = production output of dbt (clean models + the mart)
--    (dbt's dev and CI schemas, DBT_PRERNA and DBT_CI, are created by dbt.)
-- -----------------------------------------------------------------------------
CREATE DATABASE IF NOT EXISTS AUTOBID COMMENT = 'AutoBid auction data platform';
CREATE SCHEMA   IF NOT EXISTS AUTOBID.RAW       COMMENT = 'Raw data loaded from CSV files';
CREATE SCHEMA   IF NOT EXISTS AUTOBID.ANALYTICS COMMENT = 'Production dbt models';

-- -----------------------------------------------------------------------------
-- 4. Project role, with only the privileges the pipeline needs (least privilege)
-- -----------------------------------------------------------------------------
CREATE ROLE IF NOT EXISTS AUTOBID_ROLE COMMENT = 'Role used by the load script, dbt and CI';

-- Use the warehouse (run queries)
GRANT USAGE ON WAREHOUSE AUTOBID_WH TO ROLE AUTOBID_ROLE;

-- See the database, and create schemas in it (dbt makes DBT_PRERNA and DBT_CI)
GRANT USAGE, CREATE SCHEMA ON DATABASE AUTOBID TO ROLE AUTOBID_ROLE;

-- RAW: the load script creates tables, a stage (upload area) and a file format
GRANT USAGE, CREATE TABLE, CREATE STAGE, CREATE FILE FORMAT
  ON SCHEMA AUTOBID.RAW TO ROLE AUTOBID_ROLE;

-- ANALYTICS: dbt creates views (staging) and tables (mart) here in production
GRANT USAGE, CREATE TABLE, CREATE VIEW
  ON SCHEMA AUTOBID.ANALYTICS TO ROLE AUTOBID_ROLE;

-- Standard practice: custom roles roll up to SYSADMIN, so admins can manage them
GRANT ROLE AUTOBID_ROLE TO ROLE SYSADMIN;

-- Let me (the human user) switch to this role in Snowsight to look at the data
GRANT ROLE AUTOBID_ROLE TO USER "PRERNA.YANDE707";

-- -----------------------------------------------------------------------------
-- 5. Service user for code: no password, key-pair login only.
--    TYPE = SERVICE means it's a program, not a person: it can't use a
--    password or log in to the web UI.
-- -----------------------------------------------------------------------------
CREATE USER IF NOT EXISTS DBT_SVC
  TYPE              = SERVICE
  DEFAULT_ROLE      = AUTOBID_ROLE
  DEFAULT_WAREHOUSE = AUTOBID_WH
  COMMENT = 'Service user for the load script, dbt and GitHub Actions';

GRANT ROLE AUTOBID_ROLE TO USER DBT_SVC;

-- Public key: paste the contents of ~/.snowflake/dbt_svc_key.pub as ONE line,
-- WITHOUT the "-----BEGIN/END PUBLIC KEY-----" lines.
-- (A public key is not a secret, but the placeholder keeps this file reusable.)
ALTER USER DBT_SVC SET RSA_PUBLIC_KEY = '<PASTE_PUBLIC_KEY_HERE>';

-- -----------------------------------------------------------------------------
-- 6. Check: RSA_PUBLIC_KEY_FP should match the fingerprint computed locally:
--    openssl rsa -pubin -in ~/.snowflake/dbt_svc_key.pub -outform DER \
--      | openssl dgst -sha256 -binary | openssl enc -base64
-- -----------------------------------------------------------------------------
DESC USER DBT_SVC;
SHOW GRANTS TO ROLE AUTOBID_ROLE;

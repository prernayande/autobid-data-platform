"""
Load the generated CSV files into Snowflake's RAW schema.

Steps (all as service user DBT_SVC with role AUTOBID_ROLE, never ACCOUNTADMIN):
  1. create a CSV file format and an internal stage (an upload area in Snowflake)
  2. PUT each CSV file into the stage
  3. re-create each RAW table (all columns are text; dbt staging casts types)
  4. COPY INTO the table from the staged file, adding _SOURCE_FILE and _LOADED_AT

Every run is a full reload, so running it twice gives the same result.

Credentials come from environment variables (nothing secret is in this file):
  SNOWFLAKE_ACCOUNT           e.g. AHFODAU-FX97841
  SNOWFLAKE_USER              e.g. DBT_SVC
  SNOWFLAKE_PRIVATE_KEY_FILE  e.g. ~/.snowflake/dbt_svc_key.p8

Run from the repo root:
  python scripts/load_to_snowflake.py               # normal load
  python scripts/load_to_snowflake.py --bad-batch   # also append the bad rows (dbt test demo)
"""

import argparse
import csv
import os
import sys
from pathlib import Path

import snowflake.connector

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data" / "generated"
BAD_BATCH_FILE = REPO_ROOT / "data" / "bad_batch" / "auction_sales_bad.csv"

# Not secrets: these names are in snowflake/setup.sql
ROLE, WAREHOUSE, DATABASE, SCHEMA = "AUTOBID_ROLE", "AUTOBID_WH", "AUTOBID", "RAW"
STAGE, FILE_FORMAT = "RAW_STAGE", "RAW_CSV"

# RAW table name -> CSV file that fills it
TABLES = {
    "VEHICLES": DATA_DIR / "vehicles.csv",
    "AUCTION_SALES": DATA_DIR / "auction_sales.csv",
}


def connect():
    """Log in as the service user with key-pair auth. Settings come from env vars."""
    names = ["SNOWFLAKE_ACCOUNT", "SNOWFLAKE_USER", "SNOWFLAKE_PRIVATE_KEY_FILE"]
    missing = [n for n in names if not os.environ.get(n)]
    if missing:
        sys.exit(f"Missing environment variables: {', '.join(missing)}")

    return snowflake.connector.connect(
        account=os.environ["SNOWFLAKE_ACCOUNT"],
        user=os.environ["SNOWFLAKE_USER"],
        authenticator="SNOWFLAKE_JWT",
        private_key_file=os.path.expanduser(os.environ["SNOWFLAKE_PRIVATE_KEY_FILE"]),
        role=ROLE,
        warehouse=WAREHOUSE,
        database=DATABASE,
        schema=SCHEMA,
    )


def column_names(csv_path):
    """Read the CSV header and make each name a safe column name: 'Engine HP' -> 'ENGINE_HP'."""
    with open(csv_path, newline="", encoding="utf-8") as f:
        header = next(csv.reader(f))
    return [name.strip().upper().replace(" ", "_") for name in header]


def upload(cur, csv_path):
    """PUT the file into the stage. Snowflake gzips it, so it is stored as <name>.csv.gz."""
    cur.execute(f"PUT 'file://{csv_path.as_posix()}' @{STAGE} OVERWRITE = TRUE AUTO_COMPRESS = TRUE")
    return csv_path.name + ".gz"


def copy_into(cur, table, columns, staged_file):
    """COPY the staged file into the table, plus which file and when (audit columns)."""
    positions = ", ".join(f"${i}" for i in range(1, len(columns) + 1))
    cur.execute(f"""
        COPY INTO {table} ({", ".join(columns)}, _SOURCE_FILE, _LOADED_AT)
        FROM (
            SELECT {positions}, METADATA$FILENAME, CURRENT_TIMESTAMP()
            FROM @{STAGE}
        )
        FILES = ('{staged_file}')
        FILE_FORMAT = (FORMAT_NAME = {FILE_FORMAT})
        ON_ERROR = ABORT_STATEMENT
    """)


def main():
    parser = argparse.ArgumentParser(description="Load generated CSVs into Snowflake RAW.")
    parser.add_argument("--bad-batch", action="store_true",
                        help="also append data/bad_batch/auction_sales_bad.csv (dbt test demo)")
    args = parser.parse_args()

    conn = connect()
    cur = conn.cursor()
    try:
        # 1. How to read our CSVs: header row, optional quotes, empty cell = NULL
        cur.execute(f"""
            CREATE OR REPLACE FILE FORMAT {FILE_FORMAT}
              TYPE = CSV
              SKIP_HEADER = 1
              FIELD_OPTIONALLY_ENCLOSED_BY = '"'
              EMPTY_FIELD_AS_NULL = TRUE
              NULL_IF = ('')
        """)
        # 2. The upload area
        cur.execute(f"CREATE STAGE IF NOT EXISTS {STAGE}")

        # 3 + 4. For each table: upload file, re-create table (all text), copy rows in
        for table, csv_path in TABLES.items():
            columns = column_names(csv_path)
            staged_file = upload(cur, csv_path)
            column_ddl = ",\n  ".join(f"{c} VARCHAR" for c in columns)
            cur.execute(f"""
                CREATE OR REPLACE TABLE {table} (
                  {column_ddl},
                  _SOURCE_FILE VARCHAR,
                  _LOADED_AT TIMESTAMP_LTZ
                )
            """)
            copy_into(cur, table, columns, staged_file)

        # Optional: append the bad rows so dbt tests have something to catch
        if args.bad_batch:
            columns = column_names(BAD_BATCH_FILE)
            if columns != column_names(TABLES["AUCTION_SALES"]):
                sys.exit("Bad batch columns don't match AUCTION_SALES; not loading it.")
            copy_into(cur, "AUCTION_SALES", columns, upload(cur, BAD_BATCH_FILE))

        for table in TABLES:
            count = cur.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            print(f"{DATABASE}.{SCHEMA}.{table}: {count} rows")
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    main()

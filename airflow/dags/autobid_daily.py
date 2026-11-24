"""
AutoBid daily pipeline: generate data -> load into Snowflake RAW -> dbt build into ANALYTICS.

Each task just calls the script/command we already run by hand, using the project's .venv
(Airflow lives in its own .venv-airflow because its dependencies clash with dbt's).

Needs these environment variables where Airflow runs (same as the load script):
  SNOWFLAKE_ACCOUNT, SNOWFLAKE_USER, SNOWFLAKE_PRIVATE_KEY_FILE
"""

from datetime import datetime, timedelta
from pathlib import Path

from airflow.providers.standard.operators.bash import BashOperator
from airflow.sdk import DAG

REPO = Path(__file__).resolve().parents[2]          # airflow/dags/ -> repo root
PYTHON = REPO / ".venv" / "bin" / "python"
DBT = REPO / ".venv" / "bin" / "dbt"

with DAG(
    dag_id="autobid_daily",
    description="Generate auction data, load it into Snowflake, build and test dbt models",
    schedule="@daily",                     # once a day, at midnight UTC
    start_date=datetime(2026, 11, 1),
    catchup=False,                         # don't run all the missed days since start_date
    max_active_runs=1,                     # never two runs at once (they'd overwrite each other's data)
    default_args={
        "owner": "prerna",
        "retries": 1,                      # one automatic retry; every task is safe to re-run
        "retry_delay": timedelta(minutes=5),
    },
    tags=["autobid"],
) as dag:

    generate_data = BashOperator(
        task_id="generate_data",
        bash_command=f"cd {REPO} && {PYTHON} scripts/generate_auction_data.py",
    )

    load_to_snowflake = BashOperator(
        task_id="load_to_snowflake",
        bash_command=f"cd {REPO} && {PYTHON} scripts/load_to_snowflake.py",
    )

    # builds models AND runs all tests; a failing test fails this task (and the run)
    dbt_build = BashOperator(
        task_id="dbt_build",
        bash_command=f"cd {REPO}/autobid_dbt && {DBT} build --target prod",
    )

    generate_data >> load_to_snowflake >> dbt_build

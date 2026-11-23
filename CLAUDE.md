# CLAUDE.md — AutoBid Data Platform

This file gives Claude Code the context for this repo. Read it fully before every task.

## Who I am and why this project exists

- I'm Prerna, an MS Business Analytics & AI student at UTD with ~4.5 years of software engineering
  experience (C#/.NET, Java/Spring Boot, SQL Server) but **no prior data engineering experience**.
- I'm preparing for a **Copart Data Engineering Intern** interview. The recruiter will review this
  project with me in a mock interview.
- **The main goal is learning.** I must be able to explain and defend every file and decision in an
  interview. Building fast without me understanding it is a failure.

## How to work with me (important)

- **Explain in plain, simple words. No jargon** unless I ask. When you must use a term, define it in
  one line.
- **One small step at a time.** Do only the step I asked for. Don't jump ahead or build extra things.
- **Before writing code, tell me the plan in short bullets**: what goes in, what it does, what comes out.
- **After each step, point out the design choices an interviewer might ask about** and how to defend them.
- **Keep it simple.** This is a small, clear project, not big data. Prefer the simplest thing that works.
  No extra frameworks, no clever abstractions.
- **Ask before** running anything that creates or changes cloud resources (Snowflake, GitHub settings).
- If something fails, explain the error in plain words before fixing it.

## Hard rules

- **$0 only.** Never use or suggest anything that needs a credit card or a paid plan.
- **Never put secrets in the repo**: no passwords, private keys, or tokens in any committed file.
  - dbt connection lives in `~/.dbt/profiles.yml` (outside the repo).
  - Private keys live in `~/.snowflake/` (outside the repo).
  - Scripts read credentials from environment variables.
  - `.gitignore` must cover `.env`, `*.p8`, `*.pem`, `profiles.yml`, `target/`, `logs/`, `.venv/`,
    `.venv-airflow/`, `airflow/*` except `airflow/dags/`, `notes/`.
- **Language:** Python for scripts, SQL for dbt models, YAML for config. No JavaScript.
- **Never run Snowflake as ACCOUNTADMIN in code.** Use the project role (least privilege).
- Keep Snowflake costs near zero: X-Small warehouse, auto-suspend 60 seconds.

## The problem this project solves

> An online vehicle auction company gets new data every day: cars arriving at yards, lots listed, bids,
> cars sold. Raw data is messy, so analysts don't trust the numbers, and pipeline changes break dashboards
> quietly. **Question to answer: how much value does a car keep after damage, and which damage types sell
> best at auction?**

Solution: a small governed pipeline — raw CSVs → Snowflake → dbt (clean, test, document) → one business
mart — run daily by Airflow, with the same dbt project also running on BigQuery, CI tests on every pull
request, and lineage/ownership in DataHub.

## Tech stack (all free)

| Layer | Tool |
| --- | --- |
| Warehouse (main) | Snowflake (30-day trial, $400 credits, no card) |
| Warehouse (second platform) | Google BigQuery sandbox (free, no card) |
| Orchestration | Apache Airflow, run locally with `airflow standalone` (no Docker) |
| Transform + tests + docs | dbt Core (`dbt-snowflake`, `dbt-bigquery`) |
| Scripts | Python 3.11/3.12 in a `.venv` virtual environment |
| CI/CD | GitHub Actions (public repo = free) |
| Governance / catalog / lineage | DataHub open source, run locally in Docker |
| Machine | MacBook Air M4, VS Code, Docker Desktop |

**Talk-about-only (do NOT build):** Databricks, incremental models, Omni/Looker/ThoughtSpot
semantic layer, agentic analytics, data retention/archiving jobs. These go in the README as
"How this would grow in production".

## Snowflake details

- Account identifier: `AHFODAU-FX97841`
- My login user: `PRERNA.YANDE707` (human user, used only in the Snowsight web UI)
- Objects to create (in `snowflake/setup.sql`, which I run myself in Snowsight as ACCOUNTADMIN):
  - Warehouse `AUTOBID_WH` — X-Small, `AUTO_SUSPEND = 60`, `AUTO_RESUME = TRUE`, `INITIALLY_SUSPENDED = TRUE`
  - Resource monitor `AUTOBID_MONITOR` — 20 credits, suspend at 100%
  - Database `AUTOBID` with schemas `RAW` (loaded data), `ANALYTICS` (prod dbt output)
  - Role `AUTOBID_ROLE` with only the grants it needs
  - Service user `DBT_SVC` (`TYPE = SERVICE`, key-pair auth, default role `AUTOBID_ROLE`,
    default warehouse `AUTOBID_WH`) — used by the load script, dbt, and GitHub Actions

## BigQuery details (second platform)

- Use the **BigQuery sandbox** only: no billing account, no credit card. If anything asks for billing, stop.
- Sandbox limits to design around: tables expire after 60 days, and **no DML** (no INSERT/UPDATE/DELETE/MERGE).
  So on BigQuery: load with load jobs (`bq load` or the Python client), staging = views, mart = table
  (dbt rebuilds it with CREATE OR REPLACE, which is allowed). No incremental models.
- Auth: my own Google login via `gcloud auth application-default login` (dbt `method: oauth`). No key files.
- Datasets: `autobid_raw` (loaded CSVs), `dbt_prerna` (dbt dev output).
- dbt target `bq` in `~/.dbt/profiles.yml`. CI stays Snowflake-only (keep it simple).
- **Models must run on both platforms**: use portable SQL (dbt cross-database macros or plain ANSI SQL),
  no Snowflake-only functions. Source locations differ per platform, so `_sources.yml` picks database/schema
  based on `target.type`.

## Airflow details

- One DAG, `airflow/dags/autobid_daily.py`, scheduled daily, 3 tasks in order:
  `generate_data` → `load_to_snowflake` → `dbt_build` (BashOperator calling our existing scripts/commands).
- Airflow lives in its **own virtual environment** `.venv-airflow` (its dependencies clash with dbt's),
  installed with the official constraints file. `AIRFLOW_HOME` = `airflow/` in the repo;
  its database, logs and config are gitignored — only `dags/` is committed.
- Run with `airflow standalone`; UI at http://localhost:8080. Stop it when done (memory).
- Don't run Airflow and DataHub at the same time.

## Data

- `data/data.csv` — Kaggle "Car Features and MSRP" (CooperUnion/cardataset), 11,914 rows, 16 columns
  (Make, Model, Year, Engine HP, Vehicle Style, MSRP, …). Real, public data.
- `scripts/generate_auction_data.py` creates:
  - `data/generated/vehicles.csv` — a 1,000-car sample from `data.csv`, each with a generated
    `vehicle_id` and a fake 17-character VIN.
  - `data/generated/auction_sales.csv` — ~1,400 **synthetic** listings (1,000 listed once + ~400
    relistings: an unsold car is relisted 14 days later, up to 3 tries): `sale_id`, `vehicle_id`, `lot_number`,
    `damage_type` (Front End, Rear End, Side, Hail, Flood, Mechanical, Minor Dents/Scratches),
    `title_type` (Clean, Salvage), `yard_state`, `sale_date`, `bid_count`, `sale_price`, `is_sold`.
    Prices must be realistic: sale price = a damage-dependent share of MSRP, adjusted for car age,
    plus noise. Unsold lots have no sale price.
  - `data/bad_batch/auction_sales_bad.csv` — a small file with deliberately bad rows (negative price,
    duplicate sale_id, unknown vehicle_id, unknown damage type) used only to demo that dbt tests catch bad data.
  - Fixed random seed so the data is the same every run.
- Be open that auction sales are synthetic: real auction data isn't public.

## Planned repo layout

```
autobid-data-platform/
  CLAUDE.md
  README.md
  requirements.txt
  data/                      # data.csv (Kaggle) + generated CSVs
  scripts/
    generate_auction_data.py
    load_to_snowflake.py     # PUT files to a stage + COPY INTO RAW tables
    load_to_bigquery.py      # load jobs into the autobid_raw dataset
  snowflake/
    setup.sql
  autobid_dbt/               # the dbt project
    dbt_project.yml
    models/
      staging/  (_sources.yml, stg_vehicles.sql, stg_auction_sales.sql, _staging.yml)
      marts/    (mart_damage_value_retention.sql, _marts.yml)
    tests/      (singular tests, e.g. assert_sale_price_positive.sql)
  airflow/dags/autobid_daily.py
  .github/workflows/dbt_ci.yml
  datahub/                   # ingestion recipes (snowflake.yml, dbt.yml)
  notes/                     # my personal learning notes — gitignored
```

## dbt design

- `staging` models: one per source table; rename to snake_case, cast types, trim text, no business logic.
  Materialized as **views**.
- `marts/mart_damage_value_retention`: one row per damage type —
  lots listed, lots sold, sell-through rate, avg sale price, avg MSRP,
  **avg value retained % = sale_price / msrp**. Materialized as a **table**.
- Tests in YAML: `unique` + `not_null` on keys, `accepted_values` on damage_type and title_type,
  `relationships` from sales to vehicles, plus a singular test that sale_price > 0 when sold.
- Every model and key column gets a `description`; models get `meta: owner: prerna`.
- Targets in `~/.dbt/profiles.yml`: `dev` (Snowflake schema `DBT_PRERNA`), `ci` (Snowflake schema `DBT_CI`),
  `bq` (BigQuery dataset `dbt_prerna`); prod schema `ANALYTICS`.
- No dbt packages unless clearly needed (keep it simple).

## CI (GitHub Actions)

- On every pull request to `main`: install dbt, write a profile from GitHub Secrets
  (`SNOWFLAKE_ACCOUNT`, `SNOWFLAKE_USER`, `SNOWFLAKE_PRIVATE_KEY`), run `dbt build --target ci`.
- A failing test blocks the merge (branch protection on `main`).

## DataHub

- Run locally with `datahub docker quickstart` (UI at http://localhost:9002).
- Ingest: Snowflake metadata + dbt artifacts (`manifest.json`, `catalog.json`, `run_results.json`).
- Show: lineage CSV → RAW → staging → mart, owners, descriptions, a glossary term ("Value Retained"),
  and the impact of a column change.
- Stop DataHub's containers when not in use (memory on the laptop).

## Progress checklist

### Day 1 — Snowflake + dbt
- [x] 1. Python venv + requirements
- [x] 2. Snowflake setup SQL + key-pair for DBT_SVC
- [x] 3. Data generator
- [x] 4. Load script (stage + COPY INTO)
- [ ] 5. dbt project + profile + sources
- [ ] 6. Staging models
- [ ] 7. Mart model
- [ ] 8. Tests + docs + bad-data demo
- [ ] 9. Commit + push

### Day 2 — CI, BigQuery, Airflow
- [ ] 10. GitHub Actions CI + branch protection
- [ ] 11. BigQuery sandbox + load script
- [ ] 12. Same dbt project running on BigQuery (`--target bq`)
- [ ] 13. Airflow DAG running the daily pipeline

### Day 3 — Governance + story
- [ ] 14. DataHub running locally
- [ ] 15. DataHub ingestion (Snowflake + dbt)
- [ ] 16. Governance demo (change → PR → CI → lineage impact)
- [ ] 17. README with architecture diagram + "how it would grow"

Update this checklist as steps are completed.

"""
run_pipeline.py

One-command end-to-end demo run:
  1. Generate synthetic Olist-shaped orders (or load real Olist CSVs if present)
  2. Generate the simulated clickstream layer on top of those orders
  3. Load fact_user_events into a local SQLite warehouse using sql/schema.sql
  4. Run the validated funnel_query.sql and print the headline numbers
  5. Run the validated RFM engine and print segment counts

Run: python src/run_pipeline.py
"""

import sqlite3
from pathlib import Path

import pandas as pd

from sample_data import generate_orders
from generate_clickstream import generate_clickstream
from rfm_engine import compute_rfm_segments_robust

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "processed" / "warehouse.db"
RAW_ORDERS_PATH = ROOT / "data" / "raw" / "sample_orders.csv"

# Olist's payment_value column is in Brazilian Real (BRL), NOT INR.
# Mid-market BRL->INR rate, documented and dated — update this before your
# real run so the README's "as of" date stays honest. Source: ECB via
# exchangerate-api (checked Jul 2026, ~19.0 INR per BRL; the pair moves,
# so re-check at bookmyforex.com/brazilian-real/rates before your real run).
BRL_TO_INR_RATE = 19.0
BRL_TO_INR_RATE_CHECKED = "2026-07"


def load_or_generate_orders() -> pd.DataFrame:
    real_olist_path = ROOT / "data" / "raw" / "olist_orders_dataset.csv"
    if real_olist_path.exists():
        print(f"Found real Olist data at {real_olist_path} — using it.")
        orders = pd.read_csv(real_olist_path, parse_dates=["order_timestamp"])
        if "transaction_amount_inr" in orders.columns:
            print(f"Converting BRL -> INR at {BRL_TO_INR_RATE} "
                  f"(rate checked {BRL_TO_INR_RATE_CHECKED}) — "
                  "see README 'Currency conversion' note.")
            orders["transaction_amount_brl"] = orders["transaction_amount_inr"]
            orders["transaction_amount_inr"] = (
                orders["transaction_amount_brl"] * BRL_TO_INR_RATE
            ).round(2)
        return orders

    print("No real Olist CSV found — generating synthetic demo orders "
          "(see sample_data.py docstring). Swap in the real dataset when ready.")
    orders = generate_orders()
    RAW_ORDERS_PATH.parent.mkdir(parents=True, exist_ok=True)
    orders.to_csv(RAW_ORDERS_PATH, index=False)
    return orders


def main():
    orders = load_or_generate_orders()
    print(f"\n[1/5] Orders: {len(orders)} rows, {orders['user_id'].nunique()} unique customers")

    events = generate_clickstream(orders)
    events_path = ROOT / "data" / "processed" / "fact_user_events.csv"
    events_path.parent.mkdir(parents=True, exist_ok=True)
    events.to_csv(events_path, index=False)
    print(f"[2/5] Clickstream: {len(events)} events across {events['session_id'].nunique()} sessions")

    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    schema_sql = (ROOT / "sql" / "schema.sql").read_text()
    conn.executescript(schema_sql)
    events.to_sql("fact_user_events", conn, if_exists="replace", index=False)
    print(f"[3/5] Loaded fact_user_events into SQLite warehouse -> {DB_PATH}")

    funnel_sql = (ROOT / "sql" / "funnel_query.sql").read_text()
    # Run only the first SELECT statement (the funnel summary); split on the
    # blank-line-delimited step markers in the .sql file.
    first_select = funnel_sql.split("-- Step 3")[0]
    funnel_result = pd.read_sql_query(first_select, conn)
    print("\n[4/5] Funnel summary (validated session-flag CTE query):")
    print(funnel_result.to_string(index=False))

    rfm = compute_rfm_segments_robust(events)
    rfm.to_sql("dim_customer_rfm", conn, if_exists="replace", index=False)
    print(f"\n[5/5] RFM segments for {len(rfm)} purchasing customers:")
    print(rfm["Customer_Segment"].value_counts().to_string())

    conn.close()
    print(f"\nDone. SQLite warehouse ready at: {DB_PATH}")
    print("Connect Power BI to this file (or your target DW) and import "
          "dax/measures.dax for the dashboard layer.")


if __name__ == "__main__":
    main()

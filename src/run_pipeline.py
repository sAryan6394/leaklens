"""
run_pipeline.py

Runs the whole pipeline end to end:
  1. Load real Olist orders if they're present, otherwise generate synthetic orders
  2. Build the simulated clickstream layer on top of those orders
  3. Load fact_user_events into a local SQLite warehouse using sql/schema.sql
  4. Run funnel_query.sql and print the headline numbers
  5. Run the RFM engine and print segment counts

Usage: python src/run_pipeline.py
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

# Olist's payment_value column is in Brazilian Real (BRL), not INR.
# Mid-market BRL->INR rate, checked in July 2026 at roughly 19.0 INR per BRL
# (ECB data via exchangerate-api). The rate moves, so update the constant
# and the date below when re-running.
BRL_TO_INR_RATE = 19.0
BRL_TO_INR_RATE_CHECKED = "2026-07"


def load_or_generate_orders() -> pd.DataFrame:
    real_olist_path = ROOT / "data" / "raw" / "olist_orders_dataset.csv"
    if real_olist_path.exists():
        print(f"Found real Olist data at {real_olist_path}, using it.")
        orders = pd.read_csv(real_olist_path, parse_dates=["order_timestamp"])
        if "transaction_amount_inr" in orders.columns:
            print(f"Converting BRL -> INR at {BRL_TO_INR_RATE} "
                  f"(rate checked {BRL_TO_INR_RATE_CHECKED}).")
            orders["transaction_amount_brl"] = orders["transaction_amount_inr"]
            orders["transaction_amount_inr"] = (
                orders["transaction_amount_brl"] * BRL_TO_INR_RATE
            ).round(2)
        return orders

    print("No real Olist CSV found, generating synthetic demo orders instead. "
          "See the README for how to use the real dataset.")
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
    funnel_result = pd.read_sql_query(funnel_sql, conn)
    
    print("\n[4/5] Funnel summary:")
    print(funnel_result.to_string(index=False))

    rfm = compute_rfm_segments_robust(events)
    rfm.to_sql("dim_customer_rfm", conn, if_exists="replace", index=False)
    print(f"\n[5/5] RFM segments for {len(rfm)} purchasing customers:")
    print(rfm["Customer_Segment"].value_counts().to_string())

    conn.close()
    print(f"\nDone. SQLite warehouse ready at: {DB_PATH}")
    print("For Power BI, import fact_user_events.csv from data/processed/ "
          "(run src/rfm_engine.py to also write dim_customer_rfm.csv) "
          "and add the measures from dax/measures.dax.")


if __name__ == "__main__":
    main()

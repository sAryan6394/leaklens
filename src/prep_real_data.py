"""
prep_real_data.py

One-time script: joins the real Olist orders + payments + customers CSVs
into the single file run_pipeline.py expects at
data/raw/olist_orders_dataset.csv, with columns:
    order_id, user_id, order_timestamp, transaction_amount_inr

Two things this deliberately gets right that a naive join would miss:
  1. user_id comes from customer_unique_id, NOT customer_id. Olist's
     customer_id is unique PER ORDER, not per person — using it directly
     would make every order look like a different customer and Frequency
     would always read as 1, silently breaking the RFM engine.
  2. transaction_amount_inr is left as raw BRL here — the actual BRL->INR
     conversion happens in run_pipeline.py (documented, dated rate), not
     here, so there's only one place that conversion logic lives.

Run once: python src/prep_real_data.py
"""

from pathlib import Path

import pandas as pd

RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"


def main():
    orders = pd.read_csv(RAW_DIR / "olist_orders_dataset.csv",
                        usecols=["order_id", "customer_id", "order_purchase_timestamp"])
    payments = pd.read_csv(RAW_DIR / "olist_order_payments_dataset.csv",
                            usecols=["order_id", "payment_value"])
    customers = pd.read_csv(RAW_DIR / "olist_customers_dataset.csv",
                            usecols=["customer_id", "customer_unique_id"])

    # An order can have multiple payment rows (installments / split payment
    # methods) — sum to get one total per order.
    order_totals = payments.groupby("order_id", as_index=False)["payment_value"].sum()

    df = (orders
        .merge(order_totals, on="order_id", how="inner")
        .merge(customers, on="customer_id", how="inner"))

    result = pd.DataFrame({
        "order_id": df["order_id"],
        "user_id": df["customer_unique_id"],
        "order_timestamp": df["order_purchase_timestamp"],
        "transaction_amount_inr": df["payment_value"],  # raw BRL; converted in run_pipeline.py
    })

    out_path = RAW_DIR / "olist_orders_dataset.csv"
    # Overwriting the raw orders file with the joined/renamed version is
    # intentional here — run_pipeline.py looks for exactly this filename.
    result.to_csv(out_path.with_suffix(".prepped.csv"), index=False)
    print(f"Wrote {len(result)} orders for {result['user_id'].nunique()} unique customers")
    print(f"-> {out_path.with_suffix('.prepped.csv')}")
    print("\nRename this file to olist_orders_dataset.csv (replacing the raw "
        "one) before running run_pipeline.py.")


if __name__ == "__main__":
    main()
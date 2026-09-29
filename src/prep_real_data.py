"""
prep_real_data.py

Joins the real Olist orders, payments, and customers CSVs into the file
run_pipeline.py expects at data/raw/olist_orders_dataset.csv, with columns:
    order_id, user_id, order_timestamp, transaction_amount_inr

Two details in the join:
  1. user_id comes from customer_unique_id, not customer_id. Olist assigns a
     new customer_id to every order, so using it would make each order look
     like a different customer and Frequency would always be 1.
  2. transaction_amount_inr holds the raw BRL payment value. The BRL to INR
     conversion happens in run_pipeline.py, so the rate lives in one place.

The output is written as olist_orders_dataset.prepped.csv. Rename it to
olist_orders_dataset.csv to use it.

Usage: python src/prep_real_data.py
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

    # An order can have several payment rows (installments or split payment
    # methods), so sum them to get one total per order.
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
    # Saved with a .prepped.csv suffix so the raw file isn't overwritten.
    # Rename it to olist_orders_dataset.csv, the name run_pipeline.py looks for.
    result.to_csv(out_path.with_suffix(".prepped.csv"), index=False)
    print(f"Wrote {len(result)} orders for {result['user_id'].nunique()} unique customers")
    print(f"-> {out_path.with_suffix('.prepped.csv')}")
    print("\nRename this file to olist_orders_dataset.csv (replacing the raw "
        "one) before running run_pipeline.py.")


if __name__ == "__main__":
    main()
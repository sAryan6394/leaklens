"""
sample_data.py

Generates a small, CLEARLY-SYNTHETIC orders dataset shaped like the real
Olist Brazilian E-Commerce dataset (https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce).

Purpose: let the pipeline run end-to-end on day 1, before you've downloaded
the real Olist CSVs from Kaggle. Swap this out the moment you have the real
data (see README "Using the real Olist dataset").

DO NOT present numbers generated from this fixture as real business metrics
in your resume, README, or interviews. Label them "demo run on synthetic
data" until you've re-run the pipeline against the real Olist CSVs.
"""

import numpy as np
import pandas as pd

CITIES = ["Gurgaon", "Noida", "Delhi", "Lucknow", "Kanpur", "Mumbai", "Bangalore", "Pune"]
CATEGORIES = ["electronics", "fashion", "home_decor", "sports", "books", "beauty", "toys"]


def generate_orders(n_customers: int = 2000, n_orders: int = 3200, seed: int = 42) -> pd.DataFrame:
    """Order-level fact rows, shaped like Olist's orders + order_items + payments join."""
    rng = np.random.default_rng(seed)

    customer_ids = [f"USR_{100000 + i}" for i in range(n_customers)]
    order_rows = []

    start_date = pd.Timestamp("2025-09-01")
    end_date = pd.Timestamp("2026-09-01")
    date_range_days = (end_date - start_date).days

    for i in range(n_orders):
        order_id = f"ORD_{500000 + i}"
        customer_id = rng.choice(customer_ids)
        order_ts = start_date + pd.Timedelta(days=int(rng.integers(0, date_range_days)),
                                              hours=int(rng.integers(0, 24)),
                                              minutes=int(rng.integers(0, 60)))
        category = rng.choice(CATEGORIES)
        price = round(float(rng.gamma(shape=2.5, scale=800)), 2)  # right-skewed, like real cart values
        city = rng.choice(CITIES)

        order_rows.append({
            "order_id": order_id,
            "user_id": customer_id,
            "order_timestamp": order_ts,
            "category": category,
            "transaction_amount_inr": price,
            "city": city,
        })

    return pd.DataFrame(order_rows)


if __name__ == "__main__":
    df = generate_orders()
    out_path = "/home/claude/project3/data/raw/sample_orders.csv"
    df.to_csv(out_path, index=False)
    print(f"Wrote {len(df)} synthetic orders -> {out_path}")
    print(df.head())

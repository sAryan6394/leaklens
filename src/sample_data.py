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

    customer_ids = np.array([f"USR_{100000 + i}" for i in range(n_customers)])

    start_date = pd.Timestamp("2025-09-01")
    end_date = pd.Timestamp("2026-09-01")
    date_range_days = (end_date - start_date).days

    # Draw all n_orders random values in one vectorized call each, instead of
    # calling rng.choice()/rng.integers() once per row in a loop — calling
    # rng.choice() on a Python list per-row rescans/converts the whole list
    # every time, which is O(n_orders * n_customers), not O(n_orders).
    chosen_customers = rng.choice(customer_ids, size=n_orders)
    offsets_days = rng.integers(0, date_range_days, size=n_orders)
    offsets_minutes = rng.integers(0, 24 * 60, size=n_orders)  # combined hours+minutes as one offset
    chosen_categories = rng.choice(CATEGORIES, size=n_orders)
    prices = np.round(rng.gamma(shape=2.5, scale=800, size=n_orders), 2)
    chosen_cities = rng.choice(CITIES, size=n_orders)

    order_ids = [f"ORD_{500000 + i}" for i in range(n_orders)]
    order_timestamps = start_date + pd.to_timedelta(offsets_days, unit="D") \
        + pd.to_timedelta(offsets_minutes, unit="m")

    return pd.DataFrame({
        "order_id": order_ids,
        "user_id": chosen_customers,
        "order_timestamp": order_timestamps,
        "category": chosen_categories,
        "transaction_amount_inr": prices,
        "city": chosen_cities,
    })


if __name__ == "__main__":
    df = generate_orders()
    out_path = "/home/claude/project3/data/raw/sample_orders.csv"
    df.to_csv(out_path, index=False)
    print(f"Wrote {len(df)} synthetic orders -> {out_path}")
    print(df.head())

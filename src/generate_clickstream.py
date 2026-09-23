"""
generate_clickstream.py

Olist (and most public e-commerce datasets) only has order-level data —
there is no raw pre-purchase clickstream (Product View / Add to Cart /
Checkout Initiated events). This script builds that missing layer on top
of real (or sample) order data, clearly labeled as simulated.

Design choices that matter for the interview story:
  - Every COMPLETED order becomes a session that reaches Payment Completed.
  - A configurable fraction of those completed sessions include a
    non-linear browsing loop (View -> Cart -> View -> Checkout) — this is
    what makes the LEAD()-based funnel query undercount conversion, and
    is exactly the bug documented in the project's gap audit.
  - Additional ABANDONED sessions are generated at each funnel stage so the
    overall cart-abandonment rate lands near real-world e-commerce
    benchmarks (65-75%), per the project's target benchmarks.

Output: fact_user_events.csv with columns matching the spec:
  event_id, user_id, session_id, event_timestamp, event_type, cart_value_inr
"""

import numpy as np
import pandas as pd

EVENT_SEQUENCE = ["Product View", "Add to Cart", "Checkout Initiated", "Payment Completed"]


def _make_session_events(session_id, user_id, base_ts, cart_value, reach_stage,
                        non_linear, rng):
    """reach_stage: index into EVENT_SEQUENCE the session reaches (inclusive)."""
    events = []
    ts = base_ts
    for i in range(reach_stage + 1):
        events.append({
            "session_id": session_id, "user_id": user_id, "event_timestamp": ts,
            "event_type": EVENT_SEQUENCE[i], "cart_value_inr": cart_value,
        })
        ts = ts + pd.Timedelta(minutes=int(rng.integers(1, 6)))

        # Deliberately inject a non-linear loop right after "Add to Cart":
        # user goes back to browsing before continuing to checkout.
        # This is what breaks a naive LEAD()-based funnel query.
        if non_linear and EVENT_SEQUENCE[i] == "Add to Cart" and reach_stage >= 2:
            events.append({
                "session_id": session_id, "user_id": user_id, "event_timestamp": ts,
                "event_type": "Product View", "cart_value_inr": cart_value,
            })
            ts = ts + pd.Timedelta(minutes=int(rng.integers(1, 6)))
    return events


def generate_clickstream(orders: pd.DataFrame, abandonment_rate: float = 0.70,
                        non_linear_fraction: float = 0.35, seed: int = 7) -> pd.DataFrame:
    """
    orders: DataFrame with columns [order_id, user_id, order_timestamp, transaction_amount_inr]
    abandonment_rate: overall share of ALL sessions (completed + abandoned) that never pay.
    """
    rng = np.random.default_rng(seed)
    all_events = []
    sid_counter = 0

    # 1. Completed sessions — one per real order. itertuples() instead of
    # iterrows() — noticeably faster at real-dataset scale (no per-row
    # Series object construction).
    non_linear_flags = rng.random(size=len(orders)) < non_linear_fraction
    for idx, row in enumerate(orders.itertuples(index=False)):
        sid_counter += 1
        session_id = f"SES_{800000 + sid_counter}"
        all_events += _make_session_events(
            session_id, row.user_id, row.order_timestamp,
            row.transaction_amount_inr, reach_stage=3,
            non_linear=bool(non_linear_flags[idx]), rng=rng
        )

    n_completed = len(orders)
    # Solve for n_abandoned so abandonment_rate = n_abandoned / (n_abandoned + n_completed)
    n_abandoned = int(round(n_completed * abandonment_rate / (1 - abandonment_rate)))

    # 2. Abandoned sessions, spread across the three earlier drop-off points.
    #    Weighted so most abandonment happens early (product view / cart),
    #    matching typical funnel shapes.
    stage_weights = {0: 0.45, 1: 0.35, 2: 0.20}  # drop after View / after Cart / after Checkout
    user_pool = orders["user_id"].unique()  # numpy array, not a Python list
    start_ts = orders["order_timestamp"].min()
    end_ts = orders["order_timestamp"].max()
    span_days = max((end_ts - start_ts).days, 1)

    # Draw ALL random values for the n_abandoned sessions in one vectorized
    # call each, instead of once per session in the loop. Calling
    # rng.choice() on a large array/list once PER ROW rescans/converts it
    # every time — O(n_abandoned * len(user_pool)) instead of O(n_abandoned).
    # This was the actual bottleneck: with ~96K unique users and ~230K
    # abandoned sessions on the real dataset, the per-row version was doing
    # on the order of tens of billions of element-scans.
    chosen_users = rng.choice(user_pool, size=n_abandoned)
    reach_stages = rng.choice(list(stage_weights.keys()), size=n_abandoned,
                            p=list(stage_weights.values()))
    day_offsets = rng.integers(0, span_days, size=n_abandoned)
    hour_offsets = rng.integers(0, 24, size=n_abandoned)
    cart_values = np.round(rng.gamma(shape=2.2, scale=750, size=n_abandoned), 2)
    non_linear_abandoned = (rng.random(size=n_abandoned) < non_linear_fraction) & (reach_stages >= 2)
    base_timestamps = start_ts + pd.to_timedelta(day_offsets, unit="D") \
        + pd.to_timedelta(hour_offsets, unit="h")

    for i in range(n_abandoned):
        sid_counter += 1
        session_id = f"SES_{800000 + sid_counter}"
        reach_stage = int(reach_stages[i])
        cart_value = float(cart_values[i]) if reach_stage >= 1 else 0.0
        all_events += _make_session_events(
            session_id, chosen_users[i], base_timestamps[i], cart_value,
            reach_stage=reach_stage, non_linear=bool(non_linear_abandoned[i]), rng=rng
        )

    events_df = pd.DataFrame(all_events).sort_values(["session_id", "event_timestamp"]).reset_index(drop=True)
    events_df.insert(0, "event_id", [f"EVT_{900000 + i}" for i in range(len(events_df))])
    return events_df[["event_id", "user_id", "session_id", "event_timestamp", "event_type", "cart_value_inr"]]


if __name__ == "__main__":
    orders = pd.read_csv("/home/claude/project3/data/raw/sample_orders.csv", parse_dates=["order_timestamp"])
    events = generate_clickstream(orders)
    out_path = "/home/claude/project3/data/processed/fact_user_events.csv"
    events.to_csv(out_path, index=False)
    print(f"Wrote {len(events)} clickstream events across "
          f"{events['session_id'].nunique()} sessions -> {out_path}")

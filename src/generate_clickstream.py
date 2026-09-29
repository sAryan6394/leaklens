"""
generate_clickstream.py

Olist, like most public e-commerce datasets, only has order-level data. It
has no pre-purchase clickstream (Product View, Add to Cart, and Checkout
Initiated events). This script builds that layer on top of the order data,
and the events it produces are simulated.

How the simulation works:
  - Every completed order becomes a session that reaches Payment Completed.
  - A configurable fraction of those sessions include a non-linear browsing
    loop (View -> Cart -> View -> Checkout). This is the pattern that makes
    a LEAD()-based funnel query undercount conversion (see sql/GAP_AUDIT.md).
  - Extra abandoned sessions are generated at each funnel stage so the
    overall abandonment rate lands around 70%, within published cart
    abandonment benchmarks.

Output: fact_user_events.csv with columns
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

        # Inject a non-linear loop right after "Add to Cart": the user goes
        # back to browsing before continuing to checkout. This is the pattern
        # that breaks a LEAD()-based funnel query.
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
    abandonment_rate: overall share of all sessions (completed and abandoned) that never pay.
    """
    rng = np.random.default_rng(seed)
    all_events = []
    sid_counter = 0

    # 1. Completed sessions, one per real order. itertuples() avoids building
    # a Series for every row, which is noticeably faster at this size.
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

    # All random values for the abandoned sessions are drawn in one vectorized
    # call each. Calling rng.choice() once per session on a large array would
    # convert it on every call, so cost would grow as O(n_abandoned *
    # len(user_pool)). On the real dataset (about 96K users and 230K abandoned
    # sessions) that comes to tens of billions of element operations.
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

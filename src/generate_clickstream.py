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

RNG = np.random.default_rng(7)

EVENT_SEQUENCE = ["Product View", "Add to Cart", "Checkout Initiated", "Payment Completed"]


def _make_session_events(session_id, user_id, base_ts, cart_value, reach_stage,
                          non_linear=False, rng=RNG):
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

    # 1. Completed sessions — one per real order.
    for _, row in orders.iterrows():
        sid_counter += 1
        session_id = f"SES_{800000 + sid_counter}"
        non_linear = rng.random() < non_linear_fraction
        all_events += _make_session_events(
            session_id, row["user_id"], row["order_timestamp"],
            row["transaction_amount_inr"], reach_stage=3, non_linear=non_linear, rng=rng
        )

    n_completed = len(orders)
    # Solve for n_abandoned so abandonment_rate = n_abandoned / (n_abandoned + n_completed)
    n_abandoned = int(round(n_completed * abandonment_rate / (1 - abandonment_rate)))

    # 2. Abandoned sessions, spread across the three earlier drop-off points.
    #    Weighted so most abandonment happens early (product view / cart),
    #    matching typical funnel shapes.
    stage_weights = {0: 0.45, 1: 0.35, 2: 0.20}  # drop after View / after Cart / after Checkout
    user_pool = orders["user_id"].unique().tolist()
    start_ts = orders["order_timestamp"].min()
    end_ts = orders["order_timestamp"].max()
    span_days = max((end_ts - start_ts).days, 1)

    for i in range(n_abandoned):
        sid_counter += 1
        session_id = f"SES_{800000 + sid_counter}"
        user_id = rng.choice(user_pool)
        reach_stage = rng.choice(list(stage_weights.keys()), p=list(stage_weights.values()))
        base_ts = start_ts + pd.Timedelta(days=int(rng.integers(0, span_days)),
                                           hours=int(rng.integers(0, 24)))
        cart_value = round(float(rng.gamma(shape=2.2, scale=750)), 2) if reach_stage >= 1 else 0.0
        non_linear = rng.random() < non_linear_fraction and reach_stage >= 2
        all_events += _make_session_events(
            session_id, user_id, base_ts, cart_value, reach_stage=reach_stage,
            non_linear=non_linear, rng=rng
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

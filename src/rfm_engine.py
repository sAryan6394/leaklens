"""
rfm_engine.py

Validated RFM segmentation engine (see project README "Validation Notes").

Frequency uses explicit business-defined pd.cut() thresholds instead of
pd.qcut() — pd.qcut() throws ValueError: Bin edges must be unique when 80%+
of buyers are single-purchase (confirmed: pandas-dev/pandas issue #7751).
duplicates='drop' is not used as the fix because it silently changes the
bin count, which breaks a fixed labels=[1,2,3,4,5] array the moment edges
collide (pandas issue #22669).
"""

import numpy as np
import pandas as pd


def compute_rfm_segments_robust(events: pd.DataFrame, lookback_days: int = 365) -> pd.DataFrame:
    """
    events: fact_user_events-shaped DataFrame with columns
        [user_id, session_id, event_timestamp, event_type, cart_value_inr]
    Only 'Payment Completed' events count toward Frequency/Monetary.
    """
    df = events.copy()
    df["event_timestamp"] = pd.to_datetime(df["event_timestamp"])

    snapshot_date = df["event_timestamp"].max() + pd.Timedelta(days=1)
    window_start = snapshot_date - pd.Timedelta(days=lookback_days)
    df_filtered = df[df["event_timestamp"] >= window_start].copy()

    completed = df_filtered[df_filtered["event_type"] == "Payment Completed"]

    # Recency should be based on the customer's most recent activity of ANY
    # kind (not just purchases) — but Frequency/Monetary must be purchases only.
    recency_src = df_filtered.groupby("user_id")["event_timestamp"].max()
    freq_monetary = completed.groupby("user_id").agg(
        Frequency=("session_id", "nunique"),
        Monetary=("cart_value_inr", "sum"),
    )

    rfm = freq_monetary.join(recency_src.rename("last_seen"), how="left")
    rfm["Recency"] = (snapshot_date - rfm["last_seen"]).dt.days
    rfm = rfm.drop(columns=["last_seen"])

    rfm["R_Score"] = pd.qcut(rfm["Recency"], 5, labels=[5, 4, 3, 2, 1], duplicates="drop")
    # Frequency: explicit business thresholds, not qcut — see module docstring.
    rfm["F_Score"] = pd.cut(rfm["Frequency"], bins=[0, 1, 2, 4, 7, np.inf],
                             labels=[1, 2, 3, 4, 5], right=True)
    rfm["M_Score"] = pd.qcut(rfm["Monetary"].rank(method="dense"), 5, labels=[1, 2, 3, 4, 5])

    rfm["RFM_Score"] = (rfm["R_Score"].astype(str) + rfm["F_Score"].astype(str)
                         + rfm["M_Score"].astype(str))

    def assign_segment(row):
        r, f = int(row["R_Score"]), int(row["F_Score"])
        if r >= 4 and f >= 4:
            return "Champions"
        elif r >= 3 and f >= 3:
            return "Loyal Customers"
        elif r >= 4 and f == 1:
            return "New Buyers"
        elif r <= 2 and f >= 3:
            return "At Risk"
        elif r <= 2 and f <= 2:
            return "Hibernating"
        return "Need Attention"

    rfm["Customer_Segment"] = rfm.apply(assign_segment, axis=1)
    return rfm.reset_index()


if __name__ == "__main__":
    events = pd.read_csv("/home/claude/project3/data/processed/fact_user_events.csv",
                          parse_dates=["event_timestamp"])
    rfm = compute_rfm_segments_robust(events)
    out_path = "/home/claude/project3/data/processed/dim_customer_rfm.csv"
    rfm.to_csv(out_path, index=False)
    print(f"Wrote RFM table for {len(rfm)} customers -> {out_path}")
    print(rfm["Customer_Segment"].value_counts())

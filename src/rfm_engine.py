"""
rfm_engine.py

RFM segmentation engine. The reasoning behind the scoring choices is in
src/GAP_AUDIT_RFM.md.

Frequency uses fixed pd.cut() thresholds instead of pd.qcut(). qcut raises
"ValueError: Bin edges must be unique" when most buyers have a single
purchase (pandas issue #7751). duplicates='drop' doesn't fix it, because it
shrinks the bin count and breaks a fixed labels=[1,2,3,4,5] array as soon as
edges collide (pandas issue #22669).

Recency and Monetary use safe_quantile_score() below. A plain
qcut(..., duplicates='drop') has the same label mismatch, it just shows up
less often, on skewed data such as many customers sharing one Recency value.
safe_quantile_score rescales whatever bin count results onto a 1..q scale, so
it can't crash, even when every customer has the same value.

Recency is measured from each customer's last 'Payment Completed' event,
which is the standard RFM definition (days since last purchase). A customer
who only browsed recently isn't recently active for RFM purposes.
"""

import numpy as np
import pandas as pd


def safe_quantile_score(series: pd.Series, q: int = 5, ascending: bool = True) -> pd.Series:
    """
    Scores `series` from 1 to q by quantile. It doesn't crash on skewed or
    tied data, including the case where every value is identical.

    qcut runs with duplicates='drop' and no fixed labels array (the fixed
    array is what breaks, see src/GAP_AUDIT_RFM.md). Whatever number of bins
    comes out is then rescaled onto a 1..q scale. With no variance at all,
    every row gets the middle score.
    """
    # If every customer has the same value, qcut can't form even one bin (it
    # returns all NaN), so return the middle score without calling it.
    if series.nunique(dropna=True) <= 1:
        return pd.Series(int(np.ceil(q / 2)), index=series.index)

    # method='dense', not 'first': customers with identical values must stay
    # tied. 'first' would break ties by row order, the same problem described
    # in src/GAP_AUDIT_RFM.md.
    codes = pd.qcut(series.rank(method="dense"), q, labels=False, duplicates="drop")
    n_bins = int(codes.max()) + 1
    if n_bins <= 1:
        return pd.Series(int(np.ceil(q / 2)), index=series.index)
    scaled = 1 + codes * (q - 1) / (n_bins - 1)
    scaled = scaled.round().astype(int)
    if not ascending:
        scaled = (q + 1) - scaled
    return scaled


def compute_rfm_segments_robust(events: pd.DataFrame, lookback_days: int = 365) -> pd.DataFrame:
    """
    events: fact_user_events-shaped DataFrame with columns
        [user_id, session_id, event_timestamp, event_type, cart_value_inr]
    Only 'Payment Completed' events count toward Recency, Frequency, and Monetary.
    """
    df = events.copy()
    df["event_timestamp"] = pd.to_datetime(df["event_timestamp"])

    snapshot_date = df["event_timestamp"].max() + pd.Timedelta(days=1)
    window_start = snapshot_date - pd.Timedelta(days=lookback_days)
    df_filtered = df[df["event_timestamp"] >= window_start].copy()

    completed = df_filtered[df_filtered["event_type"] == "Payment Completed"]

    # Recency is days since the last purchase (standard RFM), not since the
    # last activity of any kind.
    recency_src = completed.groupby("user_id")["event_timestamp"].max()
    freq_monetary = completed.groupby("user_id").agg(
        Frequency=("session_id", "nunique"),
        Monetary=("cart_value_inr", "sum"),
    )

    rfm = freq_monetary.join(recency_src.rename("last_seen"), how="left")
    rfm["Recency"] = (snapshot_date - rfm["last_seen"]).dt.days
    rfm = rfm.drop(columns=["last_seen"])

    # Fewer days since purchase is better, so ascending=False (a low raw
    # value gets a high score).
    rfm["R_Score"] = safe_quantile_score(rfm["Recency"], q=5, ascending=False)
    # Frequency uses fixed thresholds instead of qcut (see the module docstring).
    rfm["F_Score"] = pd.cut(rfm["Frequency"], bins=[0, 1, 2, 4, 7, np.inf],
                            labels=[1, 2, 3, 4, 5], right=True)
    # Monetary: higher spend = better, so ascending=True.
    rfm["M_Score"] = safe_quantile_score(rfm["Monetary"], q=5, ascending=True)

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
    events = pd.read_csv("data/processed/fact_user_events.csv",
                        parse_dates=["event_timestamp"])
    rfm = compute_rfm_segments_robust(events)
    out_path = "data/processed/dim_customer_rfm.csv"
    rfm.to_csv(out_path, index=False)
    print(f"Wrote RFM table for {len(rfm)} customers -> {out_path}")
    print(rfm["Customer_Segment"].value_counts())
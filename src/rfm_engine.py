"""
rfm_engine.py

Validated RFM segmentation engine (see project README "Validation Notes"
and sql/GAP_AUDIT.md, src/GAP_AUDIT_RFM.md).

Frequency uses explicit business-defined pd.cut() thresholds instead of
pd.qcut() — pd.qcut() throws ValueError: Bin edges must be unique when 80%+
of buyers are single-purchase (confirmed: pandas-dev/pandas issue #7751).
duplicates='drop' is not used as the fix because it silently changes the
bin count, which breaks a fixed labels=[1,2,3,4,5] array the moment edges
collide (pandas issue #22669).

Recency and Monetary use safe_quantile_score() below instead of a plain
qcut(..., duplicates='drop'): dropping duplicate edges against a FIXED
labels array is exactly the anti-pattern that crashes Frequency (see
above) — it just crashes less often, on skewed-but-not-degenerate data
(e.g. many customers sharing the same Recency value). safe_quantile_score
rescales whatever bin count actually results onto a 1..q scale instead,
so it can never crash, including the zero-variance edge case where every
customer has an identical value. Recency is computed from each customer's
last 'Payment Completed' event only (standard RFM definition — days since
last purchase), not their last event of any kind, since a customer who
only browsed recently isn't meaningfully "recently active" for RFM
purposes.
"""

import numpy as np
import pandas as pd


def safe_quantile_score(series: pd.Series, q: int = 5, ascending: bool = True) -> pd.Series:
    """
    Quantile-scores `series` into 1..q, and CANNOT crash regardless of how
    skewed or tied the data is — including the pathological case where
    every value is identical (no variance to bin at all).

    Uses duplicates='drop' WITHOUT a fixed labels array (the mistake
    documented in src/GAP_AUDIT_RFM.md), then rescales whatever bin count
    actually results back onto a 1..q integer scale. If there's truly no
    variance, every row gets the middle score rather than raising.
    """
    # Zero variance at all (every customer identical on this metric) —
    # qcut can't form even one bin here (returns all-NaN, not one bin),
    # so short-circuit before calling it.
    if series.nunique(dropna=True) <= 1:
        return pd.Series(int(np.ceil(q / 2)), index=series.index)

    # method='dense' (not 'first') — genuinely-tied customers must stay tied.
    # Using 'first' would silently reintroduce the exact random tie-breaking
    # anti-pattern documented as the ORIGINAL bug in src/GAP_AUDIT_RFM.md.
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
    Only 'Payment Completed' events count toward Frequency/Monetary.
    """
    df = events.copy()
    df["event_timestamp"] = pd.to_datetime(df["event_timestamp"])

    snapshot_date = df["event_timestamp"].max() + pd.Timedelta(days=1)
    window_start = snapshot_date - pd.Timedelta(days=lookback_days)
    df_filtered = df[df["event_timestamp"] >= window_start].copy()

    completed = df_filtered[df_filtered["event_type"] == "Payment Completed"]

    # Recency = days since last PURCHASE (standard RFM definition), not
    # days since last activity of any kind.
    recency_src = completed.groupby("user_id")["event_timestamp"].max()
    freq_monetary = completed.groupby("user_id").agg(
        Frequency=("session_id", "nunique"),
        Monetary=("cart_value_inr", "sum"),
    )

    rfm = freq_monetary.join(recency_src.rename("last_seen"), how="left")
    rfm["Recency"] = (snapshot_date - rfm["last_seen"]).dt.days
    rfm = rfm.drop(columns=["last_seen"])

    # Recency: lower days-since-purchase = better, so ascending=False
    # (low raw value -> high score). Cannot crash, even with zero variance.
    rfm["R_Score"] = safe_quantile_score(rfm["Recency"], q=5, ascending=False)
    # Frequency: explicit business thresholds, not qcut — see module docstring.
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
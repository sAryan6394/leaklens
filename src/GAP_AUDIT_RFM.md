# Gap Audit: RFM Frequency Scoring

## The bug

A naive RFM engine scores Frequency using `pd.qcut()` to split customers
into 5 equal-sized quantile buckets:

```python
rfm['F_Score'] = pd.qcut(rfm['Frequency'], 5, labels=[1, 2, 3, 4, 5])
```

This crashes on real e-commerce data. In most e-commerce datasets, 80%+ of
customers make exactly 1 purchase. When you try to split a column where the
20th, 40th, and 60th percentile are all the same value (1), `qcut` can't
create 5 distinct bin edges, and raises:

The "obvious" quick fix — `pd.qcut(..., duplicates='drop')` — isn't a real
fix either. It silently drops the colliding edges, which shrinks the bin
count below 5. That then breaks the fixed `labels=[1,2,3,4,5]` array, since
the number of labels no longer matches the number of bins produced.

## The fix

Use explicit, business-defined thresholds instead of data-driven quantiles:
```python
rfm['F_Score'] = pd.cut(
    rfm['Frequency'],
    bins=[0, 1, 2, 4, 7, np.inf],
    labels=[1, 2, 3, 4, 5],
    right=True
)
```

`pd.cut()` with fixed bin edges doesn't care how skewed the underlying
distribution is — a 1-time buyer always lands in bin 1, a 8+ time buyer
always lands in bin 5, regardless of how many other customers share that
exact purchase count. It's also more defensible than a data-driven cut:
the bin boundaries mean something ("1 purchase," "2 purchases," "3-4
purchases"), rather than shifting depending on whatever data happens to be
loaded that day.

## Why it matters

Without this fix, the RFM engine either crashes outright on real order
data, or — if `duplicates='drop'` is used to paper over the crash — silently
produces a mismatched label array that either errors again or mis-scores
customers. See `src/rfm_engine.py` for the corrected implementation.
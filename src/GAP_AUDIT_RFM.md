# Gap audit: RFM scoring

## The bug

A naive RFM engine scores Frequency by using `pd.qcut()` to split customers into five equal-sized buckets:

```python
rfm['F_Score'] = pd.qcut(rfm['Frequency'], 5, labels=[1, 2, 3, 4, 5])
```

This crashes on real e-commerce data. In most datasets, more than 80% of customers buy exactly once. When the 20th, 40th, and 60th percentiles are all the same value (1), `qcut` can't build five distinct bin edges and raises:

```
ValueError: Bin edges must be unique
```

The obvious quick fix, `pd.qcut(..., duplicates='drop')`, doesn't solve it. It drops the colliding edges, so fewer than five bins come out, and then the fixed `labels=[1, 2, 3, 4, 5]` array no longer matches the bin count.

## The fix

Use business-defined thresholds instead of data-driven quantiles:

```python
rfm['F_Score'] = pd.cut(
    rfm['Frequency'],
    bins=[0, 1, 2, 4, 7, np.inf],
    labels=[1, 2, 3, 4, 5],
    right=True
)
```

Fixed bin edges don't care how skewed the distribution is. A one-time buyer always lands in bin 1 and a buyer with eight or more purchases always lands in bin 5, no matter how many other customers share that purchase count. The boundaries also mean something ("1 purchase", "2 purchases", "3-4 purchases") instead of shifting with whatever data happens to be loaded. See `src/rfm_engine.py` for the implementation.

## The same bug in Recency and Monetary

The threshold approach doesn't carry over to Recency or Monetary, because neither has natural business boundaries the way purchase count does. An early version scored them with `pd.qcut(..., duplicates='drop')`. That avoids the first crash but brings back the label mismatch: once edges collide, the bin count shrinks and the fixed labels array no longer fits. It reproduces on real data. A Recency column with enough tied values raises:

```
ValueError: Bin labels must be one fewer than the number of bin edges
```

### The fix

`safe_quantile_score()` in `rfm_engine.py` handles this in three steps:

1. It ranks values with `method="dense"`, so customers with identical values stay tied. Using `method="first"` would break ties arbitrarily by row order, which is the same problem the Frequency fix was meant to avoid.
2. It applies `qcut(..., duplicates="drop")` without a fixed labels array, then rescales whatever number of bins came out onto a 1 to 5 scale.
3. If a column has no variance at all (every customer identical), it returns the middle score without calling `qcut`, because `qcut` returns all NaN on a single-valued input instead of one valid bin.

The function can't crash on any distribution, including much more degenerate ones than the original Frequency case.

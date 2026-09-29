# Gap audit: SQL funnel query

## The bug

A naive funnel query uses `LEAD()` to check whether the next event in a session moves the user forward:

```sql
SELECT *,
       LEAD(event_type) OVER (PARTITION BY session_id ORDER BY event_timestamp) AS next_event
FROM fact_user_events;
```

Real browsing isn't linear. Take this session:

```
Product View → Add to Cart → Product View → Checkout Initiated → Payment Completed
```

It ends in a purchase, but `LEAD()` only looks at the immediate next row. After "Add to Cart" the next row is "Product View" (the user kept browsing before checking out), so the query flags "Add to Cart" as an abandonment. It never sees the payment at the end of the session because it only ever compares one row to the next.

## The fix

Aggregate per session instead of comparing row to row:

```sql
SELECT session_id,
       MAX(CASE WHEN event_type = 'Add to Cart' THEN 1 ELSE 0 END) AS added_to_cart,
       MAX(CASE WHEN event_type = 'Payment Completed' THEN 1 ELSE 0 END) AS completed_payment
FROM fact_user_events
GROUP BY session_id;
```

`MAX(CASE WHEN ...)` asks whether an event happened anywhere in the session, not whether it happened immediately next. Sessions that loop back to browsing before completing checkout get credited correctly.

## Impact

About 35% of completed sessions in this project's simulated data include a browsing loop after "Add to Cart". A `LEAD()`-based query would have counted every one of them as an abandonment, which inflates cart abandonment and understates conversion rate. The loop injection is in `src/generate_clickstream.py`, and the corrected query is `sql/funnel_query.sql`.

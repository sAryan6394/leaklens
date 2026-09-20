# Gap Audit: SQL Funnel Query

## The bug

A naive funnel query uses `LEAD()` to check whether the *next* event in a
session moves the user forward:

```sql
SELECT *,
       LEAD(event_type) OVER (PARTITION BY session_id ORDER BY event_timestamp) AS next_event
FROM fact_user_events;
```

This breaks on real browsing behavior. A session like:
is a completed purchase — but `LEAD()` only looks at the *immediate* next
row. After "Add to Cart," the next row is "Product View" (the user browsed
more before checking out), so a naive query flags "Add to Cart" as an
abandonment. It never sees that the session later completes, because it's
only ever comparing one row to the next, not the whole session.

## The fix

Aggregate per session instead of comparing row-to-row:

```sql
SELECT session_id,
       MAX(CASE WHEN event_type = 'Add to Cart' THEN 1 ELSE 0 END) AS added_to_cart,
       MAX(CASE WHEN event_type = 'Payment Completed' THEN 1 ELSE 0 END) AS completed_payment
FROM fact_user_events
GROUP BY session_id;
```

`MAX(CASE WHEN...)` asks "did this event happen *anywhere* in the session,"
not "does it happen immediately next." That correctly credits sessions that
loop back to browsing before completing checkout.

## Why it matters

On this project's simulated data, ~35% of completed sessions include a
browsing loop after "Add to Cart." A `LEAD()`-based query would have
misclassified all of them as abandonments — inflating cart abandonment by
a wide margin and understating conversion rate. See `src/generate_clickstream.py`
for the loop injection and `sql/funnel_query.sql` for the corrected query.
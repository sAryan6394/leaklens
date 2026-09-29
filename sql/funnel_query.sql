-- Funnel query using session-level conditional aggregation.
-- A LEAD()-based version only looks at the next row, so it flags an
-- abandonment whenever a session loops back to browsing (View -> Cart ->
-- View -> Checkout). MAX(CASE WHEN ...) per session_id avoids that.
-- Details are in sql/GAP_AUDIT.md.

-- Step 1: build the per-session flag table.
WITH SessionStageFlags AS (
    SELECT
        session_id,
        user_id,
        MIN(event_timestamp) AS session_start,
        MAX(CASE WHEN event_type = 'Product View'       THEN 1 ELSE 0 END) AS visited_product,
        MAX(CASE WHEN event_type = 'Add to Cart'         THEN 1 ELSE 0 END) AS added_to_cart,
        MAX(CASE WHEN event_type = 'Checkout Initiated'  THEN 1 ELSE 0 END) AS initiated_checkout,
        MAX(CASE WHEN event_type = 'Payment Completed'   THEN 1 ELSE 0 END) AS completed_payment,
        MAX(cart_value_inr) AS final_cart_value
    FROM fact_user_events
    GROUP BY session_id, user_id
)

-- Step 2: funnel summary with the headline dashboard numbers.
SELECT
    COUNT(DISTINCT session_id)                                              AS total_sessions,
    SUM(visited_product)                                                    AS product_view_sessions,
    SUM(CASE WHEN visited_product = 1 AND added_to_cart = 1
             THEN 1 ELSE 0 END)                                             AS cart_sessions,
    SUM(CASE WHEN added_to_cart = 1 AND initiated_checkout = 1
             THEN 1 ELSE 0 END)                                             AS checkout_sessions,
    SUM(CASE WHEN initiated_checkout = 1 AND completed_payment = 1
             THEN 1 ELSE 0 END)                                             AS payment_sessions,
    ROUND(100.0 * SUM(completed_payment) / NULLIF(SUM(visited_product), 0), 2)
                                                                             AS session_conversion_rate_pct,
    SUM(CASE WHEN added_to_cart = 1 AND completed_payment = 0
             THEN final_cart_value ELSE 0 END)                              AS lost_cart_gmv_inr
FROM SessionStageFlags;

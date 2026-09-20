-- Validated funnel query — session-flag conditional aggregation.
-- Replaces a naive LEAD()-based approach, which only inspects the
-- immediate next row and falsely flags abandonment on non-linear
-- browsing loops (View -> Cart -> View -> Checkout). Confirmed as a
-- known SQL funnel-analysis failure pattern; MAX(CASE WHEN...) per
-- session_id is the standard fix (see README "Validation Notes").

-- Step 1: build the per-session flag table (also used to populate
-- fact_session_funnel for Power BI).
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

-- Step 2: funnel summary — run this for the headline dashboard numbers.
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

-- Step 3 (separate statement): materialize per-session flags into
-- fact_session_funnel for Power BI to connect to directly.
-- INSERT INTO fact_session_funnel
-- SELECT session_id, user_id, session_start, visited_product, added_to_cart,
--        initiated_checkout, completed_payment, final_cart_value
-- FROM SessionStageFlags;

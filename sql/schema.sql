-- Warehouse schema for the LeakLens pipeline.
-- Written and tested for SQLite.

CREATE TABLE IF NOT EXISTS fact_user_events (
    event_id            VARCHAR(64)  PRIMARY KEY,
    user_id             VARCHAR(64)  NOT NULL,
    session_id          VARCHAR(64)  NOT NULL,
    event_timestamp     DATETIME     NOT NULL,
    event_type          VARCHAR(32)  NOT NULL,   -- Product View | Add to Cart | Checkout Initiated | Payment Completed
    cart_value_inr       DECIMAL(12,2) NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_fact_events_session ON fact_user_events (session_id);
CREATE INDEX IF NOT EXISTS idx_fact_events_user    ON fact_user_events (user_id);
CREATE INDEX IF NOT EXISTS idx_fact_events_type     ON fact_user_events (event_type);

-- dim_customer_rfm isn't declared here. run_pipeline.py writes it with
-- pandas .to_sql() from the RFM engine's output, so its schema comes from
-- the DataFrame. The funnel query computes session-level flags on the fly
-- (see funnel_query.sql), so there's no separate session table.
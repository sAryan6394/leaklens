-- Star Schema — E-Commerce Conversion Funnel & RFM Engine
-- Standard ANSI SQL; tested against SQLite for the local demo pipeline.
-- Compatible with MySQL 8+ / PostgreSQL with minor type substitutions
-- (VARCHAR sizes, DECIMAL vs NUMERIC) noted inline.

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

-- dim_customer_rfm is intentionally NOT declared here — run_pipeline.py
-- writes it directly via pandas .to_sql() from rfm_engine.py's output, so
-- its schema is defined by the DataFrame, not by DDL. Power BI connects
-- directly to fact_user_events (for the funnel/DAX measures) and
-- dim_customer_rfm (for segments) — there is no separate fact_session_funnel
-- table; sql/funnel_query.sql's session-flag CTE is computed on the fly.
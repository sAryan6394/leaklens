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

CREATE TABLE IF NOT EXISTS dim_customer (
    user_id         VARCHAR(64) PRIMARY KEY,
    city            VARCHAR(64),
    recency_days    INT,
    frequency       INT,
    monetary_inr    DECIMAL(12,2),
    r_score         INT,
    f_score         INT,
    m_score         INT,
    rfm_score       VARCHAR(8),
    customer_segment VARCHAR(32)
);

CREATE TABLE IF NOT EXISTS dim_product_category (
    category_id     VARCHAR(64) PRIMARY KEY,
    category_name   VARCHAR(64)
);

-- Session-level summary table populated by sql/funnel_query.sql — this is
-- the table Power BI connects to for the funnel visual and Lost GMV measure.
CREATE TABLE IF NOT EXISTS fact_session_funnel (
    session_id           VARCHAR(64) PRIMARY KEY,
    user_id              VARCHAR(64),
    session_start        DATETIME,
    visited_product       INT,
    added_to_cart         INT,
    initiated_checkout    INT,
    completed_payment     INT,
    final_cart_value_inr  DECIMAL(12,2)
);

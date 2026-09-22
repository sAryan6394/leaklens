# Pipeline Architecture

`run_pipeline.py` is the single entry point. One command runs the whole
thing end to end:

## What it does, in order

1. **Load or generate orders** — checks for a real Olist CSV at
   `data/raw/olist_orders_dataset.csv`; if absent, generates synthetic
   demo orders via `sample_data.py` instead. Either way, output is an
   `orders` DataFrame with `[order_id, user_id, order_timestamp,
   transaction_amount_inr]`.
2. **Build the clickstream layer** — `generate_clickstream.py` turns each
   completed order into a full funnel session (View → Cart → Checkout →
   Payment), plus additional abandoned sessions at each drop-off stage,
   calibrated to real cart-abandonment benchmarks. Output:
   `fact_user_events.csv`.
3. **Load the warehouse** — `sql/schema.sql` creates `fact_user_events` in
   a local SQLite file; the clickstream DataFrame is loaded straight in.
4. **Run the funnel query** — `sql/funnel_query.sql`'s session-flag CTE
   runs against the warehouse, printing total sessions, per-stage
   conversion, and Lost GMV.
5. **Run the RFM engine** — `rfm_engine.py` scores every purchasing
   customer on Recency/Frequency/Monetary and assigns a segment; results
   are written back into the same SQLite file as `dim_customer_rfm`.

## What connects to what

- **Power BI** connects directly to the SQLite file at
  `data/processed/warehouse.db` (or your target DW) — to
  `fact_user_events` for the funnel/DAX measures, and to
  `dim_customer_rfm` for segments. There's no separate aggregated table;
  DAX computes session-level rollups on the fly (see `dax/measures.dax`).
- **Swapping in real data** only touches step 1 — everything downstream
  (steps 2-5) runs unchanged once a real `orders` DataFrame is in the
  same shape. See README "Using the real Olist dataset."
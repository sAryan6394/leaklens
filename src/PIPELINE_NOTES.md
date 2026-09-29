# Pipeline notes

`run_pipeline.py` is the single entry point. One command runs the whole thing:

```bash
python src/run_pipeline.py
```

## What it does, in order

1. Load or generate orders. The script looks for a real Olist file at `data/raw/olist_orders_dataset.csv`. If it isn't there, it generates synthetic demo orders through `sample_data.py`. Either way the result is an `orders` DataFrame with `order_id`, `user_id`, `order_timestamp`, and `transaction_amount_inr`.
2. Build the clickstream layer. `generate_clickstream.py` turns each completed order into a full funnel session (View, Cart, Checkout, Payment) and adds abandoned sessions at each drop-off stage, calibrated to published cart-abandonment benchmarks. The events are saved as `fact_user_events.csv`.
3. Load the warehouse. `sql/schema.sql` creates `fact_user_events` in a local SQLite file, and the clickstream DataFrame is loaded straight into it.
4. Run the funnel query. `sql/funnel_query.sql` runs against the warehouse and prints total sessions, per-stage conversion, and Lost GMV.
5. Run the RFM engine. `rfm_engine.py` scores every purchasing customer on Recency, Frequency, and Monetary value and assigns a segment. The results go into the same SQLite file as `dim_customer_rfm`.

## How the pieces connect

Power BI has no built-in SQLite connector, so the dashboard reads two CSV files from `data/processed/`. `fact_user_events.csv` is written by `run_pipeline.py`. `dim_customer_rfm.csv` is written when you run `python src/rfm_engine.py` on its own. Measures like session conversion and Lost GMV are calculated in DAX on top of these tables (see `dax/measures.dax`).

Swapping in real data only changes step 1. Steps 2 to 5 run unchanged as long as the orders DataFrame has the same columns. See "Using the real Olist dataset" in the README.

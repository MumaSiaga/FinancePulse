# Pulse Finance — CSV-only transaction intelligence

A local Python Streamlit application with Plotly charts, merchant grouping, recurring debit detection, weekday/monthly spending patterns, outlier flags and CSV export. No database or account connection.

## Run on macOS

```bash
cd finance_intelligence_dashboard
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

Upload one or more CSV statements in the sidebar. Expected headers: `Date, Description, Amount, Balance` (`Balance` is optional). Dates like `20260717` and `17/07/2026` are supported. Debits should be negative. Data is processed in the app session, not saved to a database. The CSV download buttons let you save processed results yourself.

The payments tracker shows descriptions containing the whole word `muma` across the full uploaded history, with monthly totals and CSV export. Change the reference field to track another description. Matching ignores case and repeated whitespace and excludes longer names such as `mumandafhadzi`. The tracker uses all uploads independently of sidebar filters. Upload later statements to update it and download results to keep a copy between sessions.

## Caveats

The **Save money** tab uses the sidebar selection to build adjustable spending reduction targets by category and merchant, with transaction details and a downloadable plan. It also highlights recurring debit patterns and bank fees for review. Targets cover the selected period, exclude transfers and credits, and are scenarios rather than guaranteed or monthly savings. Review inferred categories and statement coverage before using them.

- A repeated transaction with exactly the same date, description, amount and balance is deduplicated; without unique bank transaction IDs, some genuine identical records cannot be distinguished.
- Categorisation is rule-based, so some merchants will be classified as `Other`; review results.
- Recurring transactions are inferred only from regular gaps and are not guaranteed subscriptions.
- Outlier flags are statistical indicators, not fraud findings.
- Transfers are excluded from the default spending metric but remain in the net cash flow and credits/debits chart.
- The latest listed balance depends on CSV order for transactions sharing a date; it may not reflect the actual latest balance when multiple files are combined.
- Uploaded data remains in Streamlit's active process memory during use; do not deploy publicly without authentication and appropriate privacy controls.

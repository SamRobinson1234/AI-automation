# Sales Dashboard

`main.py` cleans `messy_sales.csv`, calculates sales as quantity multiplied by unit price, and writes `cleaned_sales.csv` and `sales_by_region.csv`.

Known product categories and number words such as `three` are normalized or filled in where they can be determined. Incomplete or invalid rows and duplicate order IDs are excluded.

## Run the dashboard

Run `python main.py` from the project folder. It cleans `messy_sales.csv`, creates the sales output files, and starts the dashboard. Open [http://127.0.0.1:8000](http://127.0.0.1:8000) in your browser. The dashboard lets you filter by region, salesperson, and category, search orders and products, sort by any column, and compare regional totals. Press Ctrl+C in the terminal to stop the server.

To start only the dashboard using existing cleaned data, run `python app.py`.

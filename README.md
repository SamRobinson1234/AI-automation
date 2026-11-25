# Sales Dashboard

`main.py` cleans `sales_data/messy_sales.csv`, calculates sales as quantity multiplied by unit price, and writes the cleaned records and regional totals into the `sales_data` directory.

Known product categories and number words such as `three` are normalized or filled in where they can be determined. Incomplete or invalid rows and duplicate order IDs are excluded.

## Configuration

Edit `config.json` to change the sales directory and CSV filenames, accepted date formats, product/category and region mappings, quantity words, or dashboard template and output filenames. Set `dashboard.start_after_processing` to `false` if `python main.py` should only generate the sales files and not open the dashboard.

## Python environment

The project uses the standard library and does not require installing packages. A project virtual environment can be created with `python -m venv .venv`. In PyCharm, select `.venv\Scripts\python.exe` as the project interpreter (**Settings > Project > Python Interpreter**).

## Run the dashboard

Run `python main.py` from the project folder. It reads `sales_data/messy_sales.csv`, refreshes the output files, generates a standalone `sales_data/sales_dashboard.html`, and opens it in your browser. The dashboard works without a running web server and lets you filter by region, salesperson, product, and category; search orders and products; sort by any column; and compare regional totals. Run the script again after updating the CSV to refresh the dashboard.

To regenerate and open the dashboard from existing cleaned data without reprocessing the source CSV, run `python app.py`.

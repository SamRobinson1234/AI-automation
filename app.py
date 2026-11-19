import csv
import json
import webbrowser
from pathlib import Path


ROOT = Path(__file__).resolve().parent
with (ROOT / "config.json").open(encoding="utf-8") as config_file:
    CONFIG = json.load(config_file)

SALES_DIR = ROOT / CONFIG["sales_directory"]
DATA_FILE = SALES_DIR / CONFIG["cleaned_file"]
TEMPLATE_FILE = ROOT / CONFIG["dashboard"]["template_file"]
OUTPUT_FILE = SALES_DIR / CONFIG["dashboard"]["output_file"]


def load_sales():
    with DATA_FILE.open(newline="", encoding="utf-8-sig") as source:
        sales = list(csv.DictReader(source))
    for sale in sales:
        sale["quantity"] = int(sale["quantity"])
        sale["unit_price"] = float(sale["unit_price"])
        sale["sales_amount"] = float(sale["sales_amount"])
    return sales


def generate_dashboard():
    sales = load_sales()
    template = TEMPLATE_FILE.read_text(encoding="utf-8")
    embedded_sales = json.dumps(sales).replace("<", "\\u003c")
    if "__SALES_DATA__" not in template:
        raise ValueError(f"Dashboard data placeholder missing from {TEMPLATE_FILE}")
    OUTPUT_FILE.write_text(
        template.replace("__SALES_DATA__", embedded_sales),
        encoding="utf-8",
    )
    return OUTPUT_FILE


def main():
    dashboard_file = generate_dashboard()
    print(f"Generated dashboard at {dashboard_file}")
    if not webbrowser.open(dashboard_file.as_uri()):
        print("Open the generated dashboard file in your browser to view it.")


if __name__ == "__main__":
    main()

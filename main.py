import csv
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path


DATA_FILE = Path(__file__).with_name("messy_sales.csv")
CLEANED_FILE = Path(__file__).with_name("cleaned_sales.csv")
SUMMARY_FILE = Path(__file__).with_name("sales_by_region.csv")

PRODUCTS = {
    "laptop stand": ("Laptop Stand", "Accessories"),
    "wireless mouse": ("Wireless Mouse", "Accessories"),
    "usb-c dock": ("USB-C Dock", "Hardware"),
    "webcam": ("Webcam", "Hardware"),
    "headset": ("Headset", "Accessories"),
}
REGIONS = {"glasgow": "Glasgow", "edinburgh": "Edinburgh", "aberdeen": "Aberdeen", "dundee": "Dundee"}
NUMBER_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
                "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10}


def parse_date(value):
    value = value.strip()
    for date_format in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(value, date_format).date().isoformat()
        except ValueError:
            continue
    raise ValueError("invalid date")


def clean_row(row):
    product_key = row["Product"].strip().casefold()
    if product_key not in PRODUCTS:
        raise ValueError("unknown product")

    product, inferred_category = PRODUCTS[product_key]
    category_value = row["Category"].strip().casefold()
    if category_value:
        category = {"accessories": "Accessories", "hardware": "Hardware"}.get(category_value)
        if category is None:
            raise ValueError("unknown category")
    else:
        category = inferred_category

    quantity_value = row["Quantity"].strip().casefold()
    if quantity_value in NUMBER_WORDS:
        quantity = NUMBER_WORDS[quantity_value]
    else:
        quantity = int(quantity_value)
        if quantity <= 0:
            raise ValueError("quantity must be positive")

    price_value = row["Unit_Price"].strip().replace("£", "").replace(",", "")
    unit_price = Decimal(price_value).quantize(Decimal("0.01"))
    if unit_price < 0:
        raise ValueError("price must not be negative")

    order_id = row["Order_ID"].strip().upper()
    region_key = row["Region"].strip().casefold()
    salesperson = row["Salesperson"].strip()
    if not order_id or not salesperson or region_key not in REGIONS:
        raise ValueError("missing or invalid required field")

    return {
        "date": parse_date(row["Date"]),
        "order_id": order_id,
        "region": REGIONS[region_key],
        "salesperson": salesperson.title(),
        "product": product,
        "category": category,
        "quantity": quantity,
        "unit_price": unit_price,
    }


def main():
    region_totals = {}
    seen_orders = set()
    cleaned_rows = []
    skipped_rows = 0
    duplicate_rows = 0

    with DATA_FILE.open(newline="", encoding="utf-8-sig") as source:
        for row in csv.DictReader(source):
            try:
                cleaned = clean_row(row)
            except (ValueError, InvalidOperation):
                skipped_rows += 1
                continue

            if cleaned["order_id"] in seen_orders:
                duplicate_rows += 1
                continue
            seen_orders.add(cleaned["order_id"])

            sales_amount = cleaned["unit_price"] * cleaned["quantity"]
            cleaned_rows.append({
                **cleaned,
                "unit_price": f'{cleaned["unit_price"]:.2f}',
                "sales_amount": f"{sales_amount:.2f}",
            })
            region = cleaned["region"]
            region_totals[region] = region_totals.get(region, Decimal("0.00")) + sales_amount

    cleaned_fields = [
        "date", "order_id", "region", "salesperson", "product",
        "category", "quantity", "unit_price", "sales_amount",
    ]
    with CLEANED_FILE.open("w", newline="", encoding="utf-8") as output:
        writer = csv.DictWriter(output, fieldnames=cleaned_fields)
        writer.writeheader()
        writer.writerows(cleaned_rows)

    with SUMMARY_FILE.open("w", newline="", encoding="utf-8") as output:
        writer = csv.writer(output)
        writer.writerow(["region", "total_sales"])
        for region in sorted(region_totals):
            writer.writerow([region, f"{region_totals[region]:.2f}"])

    print("Sales by region")
    for region in sorted(region_totals):
        print(f"{region}: GBP {region_totals[region]:.2f}")
    print(f"\nCleaned {len(cleaned_rows)} sales records; skipped {skipped_rows} invalid/incomplete rows "
          f"and {duplicate_rows} duplicate rows.")
    print(f"Saved cleaned data to {CLEANED_FILE.name} and regional totals to {SUMMARY_FILE.name}.")
    print("\nStarting the sales dashboard...")
    from app import main as run_dashboard

    run_dashboard()


if __name__ == "__main__":
    main()

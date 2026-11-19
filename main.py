import csv
import json
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Dict, List, Set, Tuple, TypedDict


ROOT = Path(__file__).resolve().parent
CONFIG_FILE = ROOT / "config.json"
CLEANED_FIELDS = [
    "date", "order_id", "region", "salesperson", "product",
    "category", "quantity", "unit_price", "sales_amount",
]


class CleanedRow(TypedDict):
    date: str
    order_id: str
    region: str
    salesperson: str
    product: str
    category: str
    quantity: int
    unit_price: Decimal


def load_config() -> dict:
    with CONFIG_FILE.open(encoding="utf-8") as config_file:
        return json.load(config_file)


def parse_date(value: str, formats: List[str]) -> str:
    for date_format in formats:
        try:
            return datetime.strptime(value.strip(), date_format).date().isoformat()
        except ValueError:
            continue
    raise ValueError("invalid date")


def required_text(row: dict, column: str) -> str:
    value = row.get(column)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"missing {column}")
    return value.strip()


def build_lookups(config: dict) -> dict:
    return {
        "products": {
            name.casefold(): (details["name"], details["category"])
            for name, details in config["products"].items()
        },
        "categories": {
            name.casefold(): display_name
            for name, display_name in config["categories"].items()
        },
        "number_words": {
            name.casefold(): value
            for name, value in config["number_words"].items()
        },
        "regions": {
            name.casefold(): display_name
            for name, display_name in config["regions"].items()
        },
    }


def clean_row(row: dict, config: dict, lookups: dict) -> CleanedRow:
    products = lookups["products"]
    product_key = required_text(row, "Product").casefold()
    if product_key not in products:
        raise ValueError("unknown product")
    product, inferred_category = products[product_key]

    category_value = row.get("Category")
    if isinstance(category_value, str) and category_value.strip():
        category = lookups["categories"].get(category_value.strip().casefold())
        if category is None:
            raise ValueError("unknown category")
    else:
        category = inferred_category

    quantity_value = required_text(row, "Quantity").casefold()
    quantity = lookups["number_words"].get(quantity_value)
    if quantity is None:
        quantity = int(quantity_value)
    if quantity <= 0:
        raise ValueError("quantity must be positive")

    price_value = required_text(row, "Unit_Price").replace("£", "").replace(",", "")
    unit_price = Decimal(price_value).quantize(Decimal("0.01"))
    if not unit_price.is_finite() or unit_price < 0:
        raise ValueError("price must be a non-negative amount")

    region_key = required_text(row, "Region").casefold()
    regions = lookups["regions"]
    if region_key not in regions:
        raise ValueError("unknown region")

    return {
        "date": parse_date(required_text(row, "Date"), config["date_formats"]),
        "order_id": required_text(row, "Order_ID").upper(),
        "region": regions[region_key],
        "salesperson": required_text(row, "Salesperson").title(),
        "product": product,
        "category": category,
        "quantity": quantity,
        "unit_price": unit_price,
    }


def process_sales(
    data_file: Path, cleaned_file: Path, config: dict
) -> Tuple[int, Dict[str, Decimal], int, int]:
    lookups = build_lookups(config)
    region_totals: Dict[str, Decimal] = {}
    seen_orders: Set[str] = set()
    cleaned_count = 0
    skipped_rows = 0
    duplicate_rows = 0

    with data_file.open(newline="", encoding="utf-8-sig") as source:
        with cleaned_file.open("w", newline="", encoding="utf-8") as output:
            writer = csv.DictWriter(output, fieldnames=CLEANED_FIELDS)
            writer.writeheader()
            for row in csv.DictReader(source):
                try:
                    cleaned = clean_row(row, config, lookups)
                except (ValueError, InvalidOperation):
                    skipped_rows += 1
                    continue

                order_id = cleaned["order_id"]
                if order_id in seen_orders:
                    duplicate_rows += 1
                    continue
                seen_orders.add(order_id)

                sales_amount = cleaned["unit_price"] * cleaned["quantity"]
                writer.writerow({
                    "date": cleaned["date"],
                    "order_id": order_id,
                    "region": cleaned["region"],
                    "salesperson": cleaned["salesperson"],
                    "product": cleaned["product"],
                    "category": cleaned["category"],
                    "quantity": cleaned["quantity"],
                    "unit_price": f'{cleaned["unit_price"]:.2f}',
                    "sales_amount": f"{sales_amount:.2f}",
                })
                cleaned_count += 1
                region = cleaned["region"]
                region_totals[region] = region_totals.get(region, Decimal("0.00")) + sales_amount

    return cleaned_count, region_totals, skipped_rows, duplicate_rows


def write_summary(summary_file: Path, region_totals: Dict[str, Decimal]) -> None:
    with summary_file.open("w", newline="", encoding="utf-8") as output:
        writer = csv.writer(output)
        writer.writerow(["region", "total_sales"])
        for region in sorted(region_totals):
            writer.writerow([region, f"{region_totals[region]:.2f}"])


def print_summary(cleaned_count: int, region_totals: Dict[str, Decimal],
                  skipped_rows: int, duplicate_rows: int,
                  cleaned_file: Path, summary_file: Path) -> None:
    print("Sales by region")
    for region in sorted(region_totals):
        print(f"{region}: GBP {region_totals[region]:.2f}")
    print(f"\nCleaned {cleaned_count} sales records; skipped {skipped_rows} invalid/incomplete rows "
          f"and {duplicate_rows} duplicate rows.")
    print(f"Saved cleaned data to {cleaned_file} and regional totals to {summary_file}.")


def main() -> None:
    config = load_config()
    sales_dir = ROOT / config["sales_directory"]
    data_file = sales_dir / config["input_file"]
    cleaned_file = sales_dir / config["cleaned_file"]
    summary_file = sales_dir / config["summary_file"]
    sales_dir.mkdir(parents=True, exist_ok=True)

    cleaned_count, region_totals, skipped_rows, duplicate_rows = process_sales(
        data_file, cleaned_file, config
    )
    write_summary(summary_file, region_totals)
    print_summary(cleaned_count, region_totals, skipped_rows, duplicate_rows, cleaned_file, summary_file)

    if config["dashboard"]["start_after_processing"]:
        print("\nStarting the sales dashboard...")
        from app import main as run_dashboard

        run_dashboard()


if __name__ == "__main__":
    main()

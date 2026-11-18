import csv
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


ROOT = Path(__file__).resolve().parent
DATA_FILE = ROOT / "cleaned_sales.csv"
PAGE_FILE = ROOT / "dashboard.html"
HOST = "127.0.0.1"
PORT = 8000


class DashboardHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/":
            self.send_file(PAGE_FILE, "text/html; charset=utf-8")
        elif self.path == "/api/sales":
            self.send_sales()
        else:
            self.send_error(404)

    def send_file(self, path, content_type):
        try:
            content = path.read_bytes()
        except OSError:
            self.send_error(500, "Dashboard file is unavailable")
            return
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(content)

    def send_sales(self):
        try:
            with DATA_FILE.open(newline="", encoding="utf-8-sig") as source:
                sales = list(csv.DictReader(source))
            for sale in sales:
                sale["quantity"] = int(sale["quantity"])
                sale["unit_price"] = float(sale["unit_price"])
                sale["sales_amount"] = float(sale["sales_amount"])
            content = json.dumps(sales).encode("utf-8")
        except (OSError, KeyError, ValueError) as error:
            self.send_error(500, f"Could not load cleaned sales data: {error}")
            return

        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(content)

    def log_message(self, format, *args):
        print(f"{self.address_string()} - {format % args}")


def main():
    server = ThreadingHTTPServer((HOST, PORT), DashboardHandler)
    print(f"Sales dashboard running at http://{HOST}:{PORT}")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping dashboard.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()

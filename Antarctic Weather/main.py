import json
import urllib.error
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Lock
from time import monotonic
from urllib.parse import parse_qs, urlencode, urlsplit


ROOT = Path(__file__).resolve().parent
HOST = "127.0.0.1"
PORT = 8765
FORECAST_CACHE_SECONDS = 55 * 60
OPEN_METEO_FORECAST_DAYS = 8
REQUEST_TIMEOUT_SECONDS = 20
STATIC_FILES = {
    "/": ("dashboard.html", "text/html; charset=utf-8"),
    "/styles.css": ("styles.css", "text/css; charset=utf-8"),
    "/app.js": ("app.js", "text/javascript; charset=utf-8"),
}
FORECAST_CACHE = {}
FORECAST_CACHE_LOCK = Lock()
LOCATIONS = {
    "north": {
        "name": "North Antarctica",
        "station": "Esperanza Base",
        "latitude": -63.4,
        "longitude": -56.99,
    },
    "east": {
        "name": "East Antarctica",
        "station": "Davis Station",
        "latitude": -68.5766,
        "longitude": 77.9674,
    },
    "south": {
        "name": "South Antarctica",
        "station": "Amundsen–Scott South Pole Station",
        "latitude": -89.99,
        "longitude": 0,
    },
    "west": {
        "name": "West Antarctica",
        "station": "Rothera Research Station",
        "latitude": -67.5683,
        "longitude": -68.1256,
    },
}


def forecast_url(location):
    parameters = {
        "latitude": location["latitude"],
        "longitude": location["longitude"],
        "hourly": "temperature_2m,wind_speed_10m",
        "wind_speed_unit": "mph",
        "forecast_days": OPEN_METEO_FORECAST_DAYS,
        "timezone": "auto",
    }
    return f"https://api.open-meteo.com/v1/forecast?{urlencode(parameters)}"


def validate_forecast(forecast):
    if not isinstance(forecast, dict):
        raise ValueError("Forecast response must be a JSON object")
    hourly = forecast.get("hourly")
    if not isinstance(hourly, dict):
        raise ValueError("Forecast response is missing hourly data")
    series = (
        hourly.get("time"),
        hourly.get("temperature_2m"),
        hourly.get("wind_speed_10m"),
    )
    if not all(isinstance(values, list) for values in series):
        raise ValueError("Forecast response is missing hourly temperature or wind data")
    if len({len(values) for values in series}) != 1:
        raise ValueError("Forecast response has mismatched hourly data")
    return forecast


def get_forecast(location_key, location):
    now = monotonic()
    with FORECAST_CACHE_LOCK:
        cached = FORECAST_CACHE.get(location_key)
        if cached and now - cached[0] < FORECAST_CACHE_SECONDS:
            return cached[1]

    request = urllib.request.Request(
        forecast_url(location),
        headers={"User-Agent": "AntarcticWeatherDashboard/1.0"},
    )
    with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
        forecast = validate_forecast(json.loads(response.read()))

    forecast["location"] = {
        "name": location["name"],
        "station": location["station"],
    }
    content = json.dumps(forecast).encode("utf-8")
    with FORECAST_CACHE_LOCK:
        FORECAST_CACHE[location_key] = (monotonic(), content)
    return content


def get_locations():
    return {
        key: {
            "name": location["name"],
            "station": location["station"],
            "latitude": location["latitude"],
            "longitude": location["longitude"],
        }
        for key, location in LOCATIONS.items()
    }


class WeatherHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        request = urlsplit(self.path)
        if request.path in STATIC_FILES:
            self.send_static_file(*STATIC_FILES[request.path])
        elif request.path == "/api/locations":
            self.send_json(get_locations())
        elif request.path == "/api/forecast":
            self.send_forecast(request.query)
        else:
            self.send_error(404)

    def send_static_file(self, filename, content_type):
        try:
            content = (ROOT / filename).read_bytes()
        except OSError as error:
            self.send_error(500, f"Could not read {filename}: {error}")
            return

        self.send_content(content, content_type)

    def send_json(self, data):
        content = json.dumps(data).encode("utf-8")
        self.send_content(content, "application/json; charset=utf-8")

    def send_content(self, content, content_type):
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(content)

    def send_forecast(self, query):
        parameters = parse_qs(query)
        location_key = parameters.get("region", [""])[0]
        location = LOCATIONS.get(location_key)
        if location is None:
            self.send_error(400, "Choose a valid Antarctic region")
            return

        try:
            content = get_forecast(location_key, location)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, ValueError) as error:
            self.send_error(502, f"Weather forecast is unavailable: {error}")
            return

        self.send_content(content, "application/json; charset=utf-8")

    # noinspection PyShadowingBuiltins
    def log_message(self, format, *args):
        print(f"{self.address_string()} - {format % args}")


def main():
    missing_files = [
        filename for filename, _ in STATIC_FILES.values()
        if not (ROOT / filename).is_file()
    ]
    if missing_files:
        raise FileNotFoundError(
            f"Dashboard assets not found: {', '.join(missing_files)}"
        )
    server = ThreadingHTTPServer((HOST, PORT), WeatherHandler)
    url = f"http://{HOST}:{PORT}/"
    print(f"Antarctic Weather is available at {url}")
    print("Leave this window open while viewing the live forecast. Press Ctrl+C to stop.")
    webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping Antarctic Weather.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()

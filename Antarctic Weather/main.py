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
PAGE = ROOT / "dashboard.html"
HOST = "127.0.0.1"
PORT = 8765
FORECAST_CACHE_SECONDS = 55 * 60
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
        "forecast_days": 8,
        "timezone": "auto",
    }
    return f"https://api.open-meteo.com/v1/forecast?{urlencode(parameters)}"


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
    with urllib.request.urlopen(request, timeout=20) as response:
        forecast = json.loads(response.read())
    if not isinstance(forecast, dict):
        raise ValueError("Forecast response must be a JSON object")
    hourly = forecast.get("hourly")
    if not isinstance(hourly, dict):
        raise ValueError("Forecast response is missing hourly data")
    times = hourly.get("time")
    temperatures = hourly.get("temperature_2m")
    wind_speeds = hourly.get("wind_speed_10m")
    if not all(isinstance(values, list) for values in (times, temperatures, wind_speeds)):
        raise ValueError("Forecast response is missing hourly temperature or wind data")
    if len(times) != len(temperatures) or len(times) != len(wind_speeds):
        raise ValueError("Forecast response has mismatched hourly data")

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
        if request.path == "/":
            self.send_file()
        elif request.path == "/api/locations":
            self.send_locations()
        elif request.path == "/api/forecast":
            self.send_forecast(request.query)
        else:
            self.send_error(404)

    def send_file(self):
        try:
            content = PAGE.read_bytes()
        except OSError as error:
            self.send_error(500, f"Could not read dashboard: {error}")
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def send_locations(self):
        content = json.dumps(get_locations()).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
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

        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(content)

    # noinspection PyShadowingBuiltins
    def log_message(self, format, *args):
        print(f"{self.address_string()} - {format % args}")


def main():
    if not PAGE.is_file():
        raise FileNotFoundError(f"Dashboard page not found: {PAGE}")
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

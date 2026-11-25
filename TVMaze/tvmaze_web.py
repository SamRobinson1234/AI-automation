import json
import sys
import urllib.error
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from tvmaze import CONFIG_FILE, DISPLAY_FIELDS, find_show, load_config


ROOT = Path(__file__).resolve().parent
HOST = "127.0.0.1"
PORT = 8765
PAGE_FILE = ROOT / "tvmaze_search.html"


class TVMazeHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        request = urlsplit(self.path)
        if request.path == "/":
            self.send_page()
        elif request.path == "/api/search":
            self.search_show(request.query)
        else:
            self.send_error(404)

    def send_page(self):
        try:
            content = PAGE_FILE.read_bytes()
        except OSError as error:
            self.send_json(500, {"error": f"Could not read the search page: {error}"})
            return

        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(content)

    def search_show(self, query):
        show_name = parse_qs(query).get("q", [""])[0].strip()
        if not show_name:
            self.send_json(400, {"error": "Enter a TV show name to search."})
            return

        try:
            config = load_config()
            show = find_show(
                show_name,
                config["genre_filter"],
                config["minimum_rating"],
            )
        except (OSError, json.JSONDecodeError, urllib.error.URLError,
                TimeoutError, ValueError) as error:
            print(f"TVMaze search failed: {error}", file=sys.stderr)
            self.send_json(502, {"error": "Could not retrieve show information from TVMaze."})
            return

        if show is None:
            if config["genre_filter"]:
                genres = ", ".join(config["genre_filter"])
                message = (
                    f"No matching show found for that title and genre filter ({genres}) "
                    f"with a rating above {config['minimum_rating']}."
                )
            else:
                message = (
                    f"No matching show found with a rating above "
                    f"{config['minimum_rating']}. Try a different title."
                )
            self.send_json(200, {"show": None, "message": message})
            return

        values = {
            "title": show["name"],
            "genre": ", ".join(show["genres"]) if show["genres"] else "Not listed",
            "rating": show["rating"] if show["rating"] is not None else "Not rated",
            "premiere_date": show["premiered"] or "Unknown",
        }
        details = {
            field: values[field]
            for field in DISPLAY_FIELDS
            if config["display"][field]
        }
        self.send_json(200, {
            "show": details,
            "source": "https://www.tvmaze.com/",
        })

    def send_json(self, status, data):
        content = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(content)

    def log_message(self, format, *args):
        print(f"{self.address_string()} - {format % args}")


def main():
    if not PAGE_FILE.is_file():
        raise FileNotFoundError(f"Search page not found: {PAGE_FILE}")
    try:
        load_config()
    except (OSError, json.JSONDecodeError, ValueError) as error:
        print(f"Could not load {CONFIG_FILE.name}: {error}", file=sys.stderr)
        return 1

    server = ThreadingHTTPServer((HOST, PORT), TVMazeHandler)
    url = f"http://{HOST}:{PORT}/"
    print(f"TVMaze search is available at {url}")
    print("Leave this window open while using the search page. Press Ctrl+C to stop.")
    webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping TVMaze search.")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

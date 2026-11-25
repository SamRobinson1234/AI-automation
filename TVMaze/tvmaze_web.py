import html
import json
import logging
import sys
import urllib.error
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from tvmaze import (
    AppSettings,
    ShowDetails,
    ShowSearchResult,
    TVMazeConfig,
    configure_logging,
    find_show_with_status,
    load_config,
    load_settings,
)


class TVMazeHTTPServer(ThreadingHTTPServer):
    def __init__(
        self,
        address: tuple[str, int],
        handler_class: type[BaseHTTPRequestHandler],
        settings: AppSettings,
        page_file: Path,
    ) -> None:
        self.settings = settings
        self.page_file = page_file
        super().__init__(address, handler_class)


class TVMazeHandler(BaseHTTPRequestHandler):
    def _app_server(self) -> TVMazeHTTPServer:
        if not isinstance(self.server, TVMazeHTTPServer):
            raise RuntimeError("TVMaze request received by an unexpected server")
        return self.server

    def do_GET(self) -> None:
        request = urlsplit(self.path)
        settings = self._app_server().settings
        if request.path == settings.web.root_route:
            self.send_page()
        elif request.path == settings.web.search_route:
            self.search_json(request.query, settings)
        else:
            self.send_error(404)

    def do_POST(self) -> None:
        settings = self._app_server().settings
        if urlsplit(self.path).path != settings.web.search_route:
            self.send_error(404)
            return

        try:
            content_length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self.send_page(status=400, message="Invalid form submission.")
            return
        if content_length <= 0 or content_length > settings.web.max_request_body_bytes:
            self.send_page(status=400, message="Invalid form submission.")
            return

        try:
            form_data = self.rfile.read(content_length).decode("utf-8")
        except UnicodeDecodeError:
            self.send_page(status=400, message="Form data must be UTF-8 encoded.")
            return
        show_name = parse_qs(form_data).get("q", [""])[0].strip()
        if not show_name:
            self.send_page(status=400, message="Enter a TV show name to search.")
            return
        if len(show_name) > settings.web.max_search_name_length:
            self.send_page(
                status=400,
                message=(
                    "The show name is too long. Maximum length: "
                    f"{settings.web.max_search_name_length} characters."
                ),
                query=show_name,
            )
            return

        try:
            config, search_result = self.lookup(show_name, settings)
        except (
            OSError,
            json.JSONDecodeError,
            urllib.error.URLError,
            TimeoutError,
            ValueError,
        ) as error:
            print(f"TVMaze search failed: {error}", file=sys.stderr)
            logging.getLogger("tvmaze_app").exception(
                "Web show search failed for %r",
                show_name,
            )
            self.send_page(
                status=502,
                message="Could not retrieve show information from TVMaze.",
                is_error=True,
                query=show_name,
            )
            return

        if search_result.show is None:
            if search_result.below_minimum_rating:
                logging.getLogger("tvmaze_app").info(
                    "Web search for %r failed the minimum rating filter (rating %s)",
                    show_name,
                    (
                        search_result.rating
                        if search_result.rating is not None
                        else "Not rated"
                    ),
                )
                self.send_page(
                    message=(
                        "This show doesn't meet the minimum rating. "
                        "Please enter a better-rated show."
                    ),
                    query=show_name,
                )
                return
            logging.getLogger("tvmaze_app").info(
                "Web search returned no show matching configured filters for %r",
                show_name,
            )
            self.send_page(
                message=(
                    f"No matching show found with the configured filters "
                    f"(rating above {config.minimum_rating:g}). Try a different title."
                ),
                query=show_name,
            )
            return
        logging.getLogger("tvmaze_app").info(
            "Web search succeeded for %r (matched %r, rating %s)",
            show_name,
            search_result.show.name,
            (
                search_result.show.rating
                if search_result.show.rating is not None
                else "Not rated"
            ),
        )
        self.send_page(query=show_name, show=search_result.show, config=config)

    def send_page(
        self,
        status: int = 200,
        message: str = "",
        is_error: bool = False,
        query: str = "",
        show: ShowDetails | None = None,
        config: TVMazeConfig | None = None,
    ) -> None:
        server = self._app_server()
        settings = server.settings
        try:
            page = server.page_file.read_text(encoding="utf-8")
        except OSError as error:
            logging.getLogger("tvmaze_app").exception(
                "Could not read the search page for query %r",
                query,
            )
            self.send_json(500, {"error": f"Could not read the search page: {error}"})
            return

        details_html = ""
        source_html = ""
        if show is not None and config is not None:
            values: dict[str, str | float] = {
                "title": show.name,
                "genre": ", ".join(show.genres) if show.genres else "Not listed",
                "rating": show.rating if show.rating is not None else "Not rated",
                "premiere_date": show.premiered or "Unknown",
            }
            rows = [
                f"<dt>{html.escape(settings.display_labels[field])}</dt>"
                f"<dd>{html.escape(str(values[field]))}</dd>"
                for field in settings.display_labels
                if config.display[field]
            ]
            details_html = "\n".join(rows)
            source_url = html.escape(settings.api.source_url, quote=True)
            source_html = (
                f'Source: <a href="{source_url}" target="_blank" '
                'rel="noopener noreferrer">TVMaze</a>'
            )

        page = page.replace("__SEARCH_ROUTE__", html.escape(settings.web.search_route, quote=True))
        page = page.replace(
            "__MAX_SEARCH_NAME_LENGTH__",
            str(settings.web.max_search_name_length),
        )
        page = page.replace("__QUERY__", html.escape(query, quote=True))
        page = page.replace("__STATUS__", html.escape(message))
        page = page.replace("__STATUS_CLASS__", "error" if is_error else "")
        page = page.replace("__RESULT_HIDDEN__", "" if show is not None else "hidden")
        page = page.replace("__DETAILS__", details_html)
        page = page.replace("__SOURCE__", source_html)
        content = page.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", settings.web.html_content_type)
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", settings.web.cache_control)
        self.end_headers()
        self.wfile.write(content)

    def lookup(
        self,
        show_name: str,
        settings: AppSettings,
    ) -> tuple[TVMazeConfig, ShowSearchResult]:
        config = load_config(settings)
        search_result = find_show_with_status(
            show_name,
            config.genre_filter,
            config.minimum_rating,
            settings,
        )
        return config, search_result

    def search_json(self, query: str, settings: AppSettings) -> None:
        show_name = parse_qs(query).get("q", [""])[0].strip()
        if not show_name:
            self.send_json(400, {"error": "Enter a TV show name to search."})
            return
        if len(show_name) > settings.web.max_search_name_length:
            self.send_json(400, {"error": "The show name is too long."})
            return

        try:
            config, search_result = self.lookup(show_name, settings)
        except (
            OSError,
            json.JSONDecodeError,
            urllib.error.URLError,
            TimeoutError,
            ValueError,
        ) as error:
            print(f"TVMaze search failed: {error}", file=sys.stderr)
            logging.getLogger("tvmaze_app").exception(
                "Web show search failed for %r",
                show_name,
            )
            self.send_json(
                502,
                {"error": "Could not retrieve show information from TVMaze."},
            )
            return

        if search_result.show is None:
            self.send_json(200, {
                "show": None,
                "message": (
                    "This show doesn't meet the minimum rating. "
                    "Please enter a better-rated show."
                    if search_result.below_minimum_rating
                    else (
                        "No matching show found with the configured filters "
                        f"(rating above {config.minimum_rating:g})."
                    )
                ),
            })
            return
        show = search_result.show

        values: dict[str, str | float] = {
            "title": show.name,
            "genre": ", ".join(show.genres) if show.genres else "Not listed",
            "rating": show.rating if show.rating is not None else "Not rated",
            "premiere_date": show.premiered or "Unknown",
        }
        details = {
            field: {
                "label": settings.display_labels[field],
                "value": values[field],
            }
            for field in settings.display_labels
            if config.display[field]
        }
        self.send_json(
            200,
            {"show": details, "source": settings.api.source_url},
        )

    def send_json(self, status: int, data: dict[str, object]) -> None:
        content = json.dumps(data, ensure_ascii=False).encode("utf-8")
        settings = self._app_server().settings
        self.send_response(status)
        self.send_header("Content-Type", settings.web.json_content_type)
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", settings.web.cache_control)
        self.end_headers()
        self.wfile.write(content)

    def log_message(self, format_string: str, *args: object) -> None:
        logging.getLogger("tvmaze_app").info(
            "%s %s %s",
            self.address_string(),
            self.command,
            urlsplit(self.path).path,
        )


def main() -> int:
    try:
        settings = load_settings()
        load_config(settings)
    except (OSError, json.JSONDecodeError, ValueError) as error:
        print(f"Could not load TVMaze configuration: {error}", file=sys.stderr)
        return 1

    try:
        logger = configure_logging(settings)
    except (OSError, ValueError) as error:
        print(f"Could not initialize application logging: {error}", file=sys.stderr)
        return 1

    page_file = Path(__file__).resolve().with_name(settings.web.page_filename)
    if not page_file.is_file():
        raise FileNotFoundError(f"Search page not found: {page_file}")

    server = TVMazeHTTPServer(
        (settings.web.host, settings.web.port),
        TVMazeHandler,
        settings,
        page_file,
    )
    url = f"http://{settings.web.host}:{settings.web.port}{settings.web.root_route}"
    logger.info("Starting TVMaze web search at %s", url)
    print(f"TVMaze search is available at {url}")
    print("Leave this window open while using the search page. Press Ctrl+C to stop.")
    webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("TVMaze web search stopped by user")
        print("\nStopping TVMaze search.")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

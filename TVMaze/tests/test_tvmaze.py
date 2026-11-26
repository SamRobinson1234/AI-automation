import unittest
import json
import logging
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
from unittest.mock import patch
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from main import build_output, default_output_path, summarize_shows
from tvmaze import (
    ShowDetails,
    ShowSearchResult,
    configure_logging,
    find_show,
    find_show_with_status,
    load_settings,
)
from tvmaze_web import TVMazeHandler, TVMazeHTTPServer


class Response:
    def __init__(self, payload: object) -> None:
        self.payload = payload

    def __enter__(self) -> "Response":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


class TVMazeTests(unittest.TestCase):
    def test_application_settings_are_loaded_from_json(self) -> None:
        settings = load_settings()

        self.assertEqual(settings.api.search_url, "https://api.tvmaze.com/search/shows")
        self.assertEqual(settings.api.request_timeout_seconds, 20)
        self.assertEqual(settings.web.host, "127.0.0.1")
        self.assertEqual(settings.web.port, 8765)
        self.assertEqual(settings.log_filename, "runlog")

    def test_application_log_writes_entries_to_configured_runlog(self) -> None:
        settings = load_settings()
        with TemporaryDirectory() as temporary_directory:
            log_path = Path(temporary_directory) / settings.log_filename
            logger = configure_logging(settings, log_path)

            try:
                logger.info("test log entry")
                for handler in logger.handlers:
                    handler.flush()

                self.assertIn("test log entry", log_path.read_text(encoding="utf-8"))
            finally:
                for handler in logger.handlers[:]:
                    logger.removeHandler(handler)
                    handler.close()

    def test_search_skips_shows_at_or_below_minimum_rating(self) -> None:
        payload = [
            {"show": {"name": "At threshold", "genres": [], "rating": {"average": 8}}},
            {"show": {"name": "Unrated", "genres": [], "rating": {"average": None}}},
            {"show": {"name": "Above threshold", "genres": [], "rating": {"average": 8.1}}},
        ]
        with patch("tvmaze.urllib.request.urlopen", return_value=Response(payload)):
            show = find_show("Example", minimum_rating=8)

        self.assertIsNotNone(show)
        assert show is not None
        self.assertEqual(show.name, "Above threshold")

    def test_search_returns_none_when_no_result_passes_filters(self) -> None:
        payload = [
            {"show": {"name": "Below threshold", "genres": ["Drama"], "rating": {"average": 7}}},
        ]
        with patch("tvmaze.urllib.request.urlopen", return_value=Response(payload)):
            show = find_show("Example", ["comedy"], 8)

        self.assertIsNone(show)

    def test_search_reports_when_matching_show_is_below_minimum_rating(self) -> None:
        payload = [
            {
                "show": {
                    "name": "Example",
                    "genres": ["Comedy"],
                    "rating": {"average": 7.5},
                },
            },
        ]
        with patch("tvmaze.urllib.request.urlopen", return_value=Response(payload)):
            result = find_show_with_status("Example", ["comedy"], 8)

        self.assertIsNone(result.show)
        self.assertTrue(result.below_minimum_rating)

    def test_schedule_summary_deduplicates_shows_and_sorts_air_times(self) -> None:
        settings = load_settings()
        schedule = [
            {
                "airtime": "21:00",
                "show": {
                    "id": 7,
                    "name": "Example",
                    "genres": ["Drama"],
                    "rating": {"average": 8.5},
                },
            },
            {
                "airtime": "19:00",
                "show": {
                    "id": 7,
                    "name": "Example",
                    "genres": ["Drama"],
                    "rating": {"average": 8.5},
                },
            },
        ]

        output = build_output(date(2026, 11, 26), schedule, settings)

        self.assertEqual(output["country"], "GB")
        self.assertEqual(len(output["shows"]), 1)
        self.assertEqual(output["shows"][0]["airing_times"], ["19:00", "21:00"])
        self.assertEqual(len(summarize_shows(schedule)), 1)

    def test_default_schedule_output_uses_configured_onedrive_location(self) -> None:
        settings = load_settings()

        output_path = default_output_path(settings, {"OneDrive": "C:/OneDrive"})

        self.assertEqual(
            output_path.as_posix(),
            "C:/OneDrive/Documents/TVMaze/schedule.json",
        )

    def test_web_page_and_search_endpoint_use_loaded_settings(self) -> None:
        settings = load_settings()
        page_file = Path(__file__).resolve().parents[1] / settings.web.page_filename
        server = TVMazeHTTPServer(
            ("127.0.0.1", 0),
            TVMazeHandler,
            settings,
            page_file,
        )
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base_url = f"http://127.0.0.1:{server.server_address[1]}"

        try:
            with urlopen(base_url + settings.web.root_route, timeout=5) as response:
                page = response.read()
            self.assertIn(
                (
                    f'method="post" action="{settings.web.search_route}"'
                ).encode("utf-8"),
                page,
            )
            self.assertNotIn(b"__SEARCH_ROUTE__", page)
            self.assertNotIn(b"<script>", page)

            show = ShowDetails(
                name="Example",
                rating=9.0,
                genres=("Drama",),
                premiered="2020-01-02",
            )
            post_request = Request(
                base_url + settings.web.search_route,
                data=urlencode({"q": "Example"}).encode("utf-8"),
            )
            with patch(
                "tvmaze_web.find_show_with_status",
                return_value=ShowSearchResult(show, False),
            ), patch.object(
                logging.getLogger("tvmaze_app"),
                "info",
            ) as log_info:
                with urlopen(post_request, timeout=5) as response:
                    search_page = response.read()
                log_info.assert_any_call(
                    "Web search succeeded for %r (matched %r, rating %s)",
                    "Example",
                    "Example",
                    9.0,
                )
            self.assertIn(b"<dt>Title</dt>", search_page)
            self.assertIn(b"Example", search_page)
            self.assertIn(b"<dt>Premiere date</dt>", search_page)
            self.assertNotIn(b"<script>", search_page)

            show = ShowDetails(
                name="Example",
                rating=9.0,
                genres=("Drama",),
                premiered="2020-01-02",
            )
            with patch(
                "tvmaze_web.find_show_with_status",
                return_value=ShowSearchResult(show, False),
            ):
                with urlopen(
                    f"{base_url}{settings.web.search_route}?q=Example",
                    timeout=5,
                ) as response:
                    result = json.loads(response.read())

            self.assertEqual(
                result,
                {
                    "show": {
                        "title": {"label": "Title", "value": "Example"},
                        "genre": {"label": "Genres", "value": "Drama"},
                        "rating": {"label": "Rating", "value": 9.0},
                        "premiere_date": {
                            "label": "Premiere date",
                            "value": "2020-01-02",
                        },
                    },
                    "source": settings.api.source_url,
                },
            )

            no_match_request = Request(
                base_url + settings.web.search_route,
                data=urlencode({"q": "Low Rated Show"}).encode("utf-8"),
            )
            with patch(
                "tvmaze_web.find_show_with_status",
                return_value=ShowSearchResult(None, True, 7.5),
            ), patch.object(
                logging.getLogger("tvmaze_app"),
                "info",
            ) as log_info:
                with urlopen(no_match_request, timeout=5) as response:
                    low_rating_page = response.read()
            self.assertIn(b"Please enter a better-rated show.", low_rating_page)
            log_info.assert_any_call(
                "Web search for %r failed the minimum rating filter (rating %s)",
                "Low Rated Show",
                7.5,
            )

            no_match_request = Request(
                base_url + settings.web.search_route,
                data=urlencode({"q": "Heroes"}).encode("utf-8"),
            )
            with patch(
                "tvmaze_web.find_show_with_status",
                return_value=ShowSearchResult(None, False),
            ), patch.object(
                logging.getLogger("tvmaze_app"),
                "info",
            ) as log_info:
                with urlopen(no_match_request, timeout=5) as response:
                    self.assertEqual(response.status, 200)
                log_info.assert_any_call(
                    "Web search returned no show matching configured filters for %r",
                    "Heroes",
                )
        finally:
            server.shutdown()
            server.server_close()
            thread.join()


if __name__ == "__main__":
    unittest.main()

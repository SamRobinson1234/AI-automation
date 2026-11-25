import json
import logging
import math
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence


SETTINGS_FILE = Path(__file__).resolve().with_name("app_settings.json")


@dataclass(frozen=True)
class ApiSettings:
    search_url: str
    schedule_url: str
    request_timeout_seconds: int
    search_user_agent: str
    schedule_user_agent: str
    source_url: str


@dataclass(frozen=True)
class WebSettings:
    host: str
    port: int
    page_filename: str
    root_route: str
    search_route: str
    html_content_type: str
    json_content_type: str
    cache_control: str
    max_search_name_length: int
    max_request_body_bytes: int


@dataclass(frozen=True)
class ScheduleSettings:
    country_code: str
    one_drive_environment_variables: tuple[str, ...]
    documents_folder: str
    output_folder: str
    output_filename: str
    date_offset_days: int


@dataclass(frozen=True)
class AppSettings:
    api: ApiSettings
    web: WebSettings
    schedule: ScheduleSettings
    report_heading: str
    log_filename: str
    log_level: str
    log_format: str
    display_labels: Mapping[str, str]
    user_config_filename: str


@dataclass(frozen=True)
class ShowDetails:
    name: str
    rating: float | None
    genres: tuple[str, ...]
    premiered: str | None


@dataclass(frozen=True)
class TVMazeConfig:
    display: Mapping[str, bool]
    genre_filter: tuple[str, ...]
    minimum_rating: float


def _require_mapping(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ValueError(f"{label} must be a JSON object with string keys")
    return value


def _require_string(mapping: Mapping[str, object], key: str) -> str:
    value = mapping.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Setting '{key}' must be a non-empty string")
    return value


def _require_integer(mapping: Mapping[str, object], key: str) -> int:
    value = mapping.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"Setting '{key}' must be an integer")
    return value


def _require_string_tuple(mapping: Mapping[str, object], key: str) -> tuple[str, ...]:
    value = mapping.get(key)
    if not isinstance(value, list) or not all(
        isinstance(item, str) and item.strip() for item in value
    ):
        raise ValueError(f"Setting '{key}' must be a list of non-empty strings")
    return tuple(value)


def load_settings() -> AppSettings:
    with SETTINGS_FILE.open(encoding="utf-8") as settings_file:
        raw_settings: object = json.load(settings_file)
    settings = _require_mapping(raw_settings, "Application settings")
    api = _require_mapping(settings.get("api"), "Settings 'api'")
    web = _require_mapping(settings.get("web"), "Settings 'web'")
    schedule = _require_mapping(settings.get("schedule"), "Settings 'schedule'")
    labels = _require_mapping(settings.get("display_labels"), "Settings 'display_labels'")
    if not all(isinstance(label, str) and label.strip() for label in labels.values()):
        raise ValueError("Setting 'display_labels' values must be non-empty strings")

    timeout = _require_integer(api, "request_timeout_seconds")
    port = _require_integer(web, "port")
    max_search_name_length = _require_integer(web, "max_search_name_length")
    max_request_body_bytes = _require_integer(web, "max_request_body_bytes")
    date_offset = _require_integer(schedule, "date_offset_days")
    if (
        timeout <= 0
        or not 1 <= port <= 65535
        or max_search_name_length <= 0
        or max_request_body_bytes <= 0
        or date_offset < 0
    ):
        raise ValueError("Timeout, web port, or schedule date offset is out of range")

    return AppSettings(
        api=ApiSettings(
            search_url=_require_string(api, "search_url"),
            schedule_url=_require_string(api, "schedule_url"),
            request_timeout_seconds=timeout,
            search_user_agent=_require_string(api, "search_user_agent"),
            schedule_user_agent=_require_string(api, "schedule_user_agent"),
            source_url=_require_string(api, "source_url"),
        ),
        web=WebSettings(
            host=_require_string(web, "host"),
            port=port,
            page_filename=_require_string(web, "page_filename"),
            root_route=_require_string(web, "root_route"),
            search_route=_require_string(web, "search_route"),
            html_content_type=_require_string(web, "html_content_type"),
            json_content_type=_require_string(web, "json_content_type"),
            cache_control=_require_string(web, "cache_control"),
            max_search_name_length=max_search_name_length,
            max_request_body_bytes=max_request_body_bytes,
        ),
        schedule=ScheduleSettings(
            country_code=_require_string(schedule, "country_code"),
            one_drive_environment_variables=_require_string_tuple(
                schedule, "one_drive_environment_variables"
            ),
            documents_folder=_require_string(schedule, "documents_folder"),
            output_folder=_require_string(schedule, "output_folder"),
            output_filename=_require_string(schedule, "output_filename"),
            date_offset_days=date_offset,
        ),
        report_heading=_require_string(settings, "report_heading"),
        log_filename=_require_string(settings, "log_filename"),
        log_level=_require_string(settings, "log_level").upper(),
        log_format=_require_string(settings, "log_format"),
        display_labels={key: str(label) for key, label in labels.items()},
        user_config_filename=_require_string(settings, "user_config_filename"),
    )


def configure_logging(
    settings: AppSettings,
    log_path: Path | None = None,
) -> logging.Logger:
    log_level = logging.getLevelName(settings.log_level)
    if not isinstance(log_level, int):
        raise ValueError(f"Unsupported log level: {settings.log_level}")

    output_path = log_path or SETTINGS_FILE.with_name(settings.log_filename)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    file_handler = logging.FileHandler(output_path, encoding="utf-8")
    file_handler.setFormatter(logging.Formatter(settings.log_format))

    logger = logging.getLogger("tvmaze_app")
    for existing_handler in logger.handlers[:]:
        logger.removeHandler(existing_handler)
        existing_handler.close()
    logger.setLevel(log_level)
    logger.propagate = False
    logger.addHandler(file_handler)
    return logger


def load_config(settings: AppSettings | None = None) -> TVMazeConfig:
    app_settings = settings or load_settings()
    config_file = SETTINGS_FILE.with_name(app_settings.user_config_filename)
    with config_file.open(encoding="utf-8") as config_stream:
        raw_config: object = json.load(config_stream)
    config = _require_mapping(raw_config, "Configuration")
    display = _require_mapping(config.get("display"), "Configuration 'display'")
    if set(display) != set(app_settings.display_labels):
        raise ValueError("Configuration 'display' must contain every configured report field")
    if not all(isinstance(enabled, bool) for enabled in display.values()):
        raise ValueError("Every configuration value in 'display' must be true or false")

    raw_genres = config.get("genre_filter")
    if not isinstance(raw_genres, list) or not all(
        isinstance(genre, str) and genre.strip() for genre in raw_genres
    ):
        raise ValueError("Configuration 'genre_filter' must be a list of genre names")

    raw_minimum_rating = config.get("minimum_rating")
    if (
        isinstance(raw_minimum_rating, bool)
        or not isinstance(raw_minimum_rating, (int, float))
        or not math.isfinite(raw_minimum_rating)
        or not 0 <= raw_minimum_rating <= 10
    ):
        raise ValueError("Configuration 'minimum_rating' must be a number from 0 to 10")

    return TVMazeConfig(
        display={field: enabled for field, enabled in display.items() if isinstance(enabled, bool)},
        genre_filter=tuple(genre.strip().casefold() for genre in raw_genres),
        minimum_rating=float(raw_minimum_rating),
    )


def search_url(show_name: str, settings: AppSettings | None = None) -> str:
    api = (settings or load_settings()).api
    parameters = urllib.parse.urlencode({"q": show_name})
    return f"{api.search_url}?{parameters}"


def find_show(
    show_name: str,
    genre_filter: Sequence[str] = (),
    minimum_rating: float | None = None,
    settings: AppSettings | None = None,
) -> ShowDetails | None:
    app_settings = settings or load_settings()
    request = urllib.request.Request(
        search_url(show_name, app_settings),
        headers={"User-Agent": app_settings.api.search_user_agent},
    )
    with urllib.request.urlopen(
        request, timeout=app_settings.api.request_timeout_seconds
    ) as response:
        raw_results: object = json.loads(response.read())

    if not isinstance(raw_results, list):
        raise ValueError("TVMaze returned an unexpected search format")

    required_genres = {genre.casefold() for genre in genre_filter}
    for result in raw_results:
        result_object = _require_mapping(result, "TVMaze search result")
        show = _require_mapping(result_object.get("show"), "TVMaze show")
        name = _require_string(show, "name")

        raw_genres = show.get("genres")
        genres = raw_genres if raw_genres is not None else []
        if not isinstance(genres, list) or not all(isinstance(item, str) for item in genres):
            raise ValueError("TVMaze returned invalid show genres")

        raw_rating = show.get("rating")
        rating = _require_mapping(raw_rating, "TVMaze rating") if raw_rating is not None else {}
        raw_average = rating.get("average")
        if raw_average is not None and (
            isinstance(raw_average, bool)
            or not isinstance(raw_average, (int, float))
            or not math.isfinite(raw_average)
        ):
            raise ValueError("TVMaze returned an invalid rating value")
        average_rating = float(raw_average) if raw_average is not None else None

        if required_genres and not required_genres.intersection(
            genre.casefold() for genre in genres
        ):
            continue
        if minimum_rating is not None and (
            average_rating is None or average_rating <= minimum_rating
        ):
            continue

        raw_premiered = show.get("premiered")
        if raw_premiered is not None and not isinstance(raw_premiered, str):
            raise ValueError("TVMaze returned an invalid premiere date")
        return ShowDetails(
            name=name,
            rating=average_rating,
            genres=tuple(genres),
            premiered=raw_premiered,
        )
    return None


def main() -> int:
    logger: logging.Logger | None = None
    try:
        settings = load_settings()
        logger = configure_logging(settings)
        logger.info("Starting terminal show lookup")
        config = load_config(settings)
    except (OSError, json.JSONDecodeError, ValueError) as error:
        if logger is not None:
            logger.exception("Could not load TVMaze configuration")
        print(f"Could not load TVMaze configuration: {error}", file=sys.stderr)
        return 1

    show_name = input("Enter a TV show name: ").strip()
    if not show_name:
        logger.warning("Terminal lookup was submitted with an empty show name")
        print("Please enter a TV show name.", file=sys.stderr)
        return 1

    try:
        show = find_show(
            show_name,
            config.genre_filter,
            config.minimum_rating,
            settings,
        )
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, ValueError) as error:
        logger.exception("Terminal search failed")
        print(f"Could not retrieve the TV show: {error}", file=sys.stderr)
        return 1

    if show is None:
        logger.info("Terminal search returned no show matching configured filters")
        print(
            f"No TV show found for {show_name!r} matching the configured filters "
            f"(rating above {config.minimum_rating:g})."
        )
        return 1

    logger.info("Terminal search succeeded for show %r", show.name)
    print(f"\n{settings.report_heading}")
    values = {
        "title": show.name,
        "genre": ", ".join(show.genres) if show.genres else "Not listed",
        "rating": show.rating if show.rating is not None else "Not rated",
        "premiere_date": show.premiered or "Unknown",
    }
    for field, label in settings.display_labels.items():
        if config.display[field]:
            print(f"{label}: {values[field]}")
    print(f"Source: {settings.api.source_url}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

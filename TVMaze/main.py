import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Mapping, Sequence, TypedDict

from tvmaze import AppSettings, configure_logging, load_settings


@dataclass(frozen=True)
class ShowSummary:
    identifier: int | str
    name: str
    genres: tuple[str, ...]
    rating: float | None
    airings: tuple[str | None, ...]


class ScheduleShowOutput(TypedDict):
    name: str
    airing_times: list[str]
    genres: list[str]
    rating: float | None


class ScheduleOutput(TypedDict):
    date: str
    country: str
    shows: list[ScheduleShowOutput]
    source: str


def _require_mapping(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ValueError(f"{label} must be a JSON object")
    return value


def schedule_url(schedule_date: date, settings: AppSettings) -> str:
    parameters = urllib.parse.urlencode({
        "country": settings.schedule.country_code,
        "date": schedule_date.isoformat(),
    })
    return f"{settings.api.schedule_url}?{parameters}"


def fetch_schedule(schedule_date: date, settings: AppSettings) -> list[dict[str, object]]:
    request = urllib.request.Request(
        schedule_url(schedule_date, settings),
        headers={"User-Agent": settings.api.schedule_user_agent},
    )
    with urllib.request.urlopen(
        request, timeout=settings.api.request_timeout_seconds
    ) as response:
        raw_schedule: object = json.loads(response.read())

    if not isinstance(raw_schedule, list):
        raise ValueError("TVMaze returned an unexpected schedule format")
    return [
        _require_mapping(episode, "TVMaze schedule item")
        for episode in raw_schedule
    ]


def show_rating(show: Mapping[str, object]) -> float | None:
    raw_rating = show.get("rating")
    rating = _require_mapping(raw_rating, "TVMaze rating") if raw_rating is not None else {}
    average = rating.get("average")
    if average is None:
        return None
    if isinstance(average, bool) or not isinstance(average, (int, float)):
        raise ValueError("TVMaze returned an invalid show rating")
    return float(average)


def show_genres(show: Mapping[str, object]) -> tuple[str, ...]:
    raw_genres = show.get("genres")
    genres = raw_genres if raw_genres is not None else []
    if not isinstance(genres, list) or not all(isinstance(item, str) for item in genres):
        raise ValueError("TVMaze returned invalid show genres")
    return tuple(genres)


def summarize_shows(
    schedule: Sequence[Mapping[str, object]],
) -> list[ShowSummary]:
    shows: dict[int | str, ShowSummary] = {}
    for episode in schedule:
        show = _require_mapping(episode.get("show"), "TVMaze schedule show")
        identifier = show.get("id")
        name = show.get("name")
        if (
            isinstance(identifier, bool)
            or not isinstance(identifier, (int, str))
            or not isinstance(name, str)
        ):
            raise ValueError("TVMaze returned a show without a valid ID or name")

        airtime = episode.get("airtime")
        if airtime is not None and not isinstance(airtime, str):
            raise ValueError("TVMaze returned an invalid episode airtime")
        summary = shows.get(identifier)
        if summary is None:
            summary = ShowSummary(
                identifier=identifier,
                name=name,
                genres=show_genres(show),
                rating=show_rating(show),
                airings=(airtime,),
            )
        else:
            summary = ShowSummary(
                identifier=summary.identifier,
                name=summary.name,
                genres=summary.genres,
                rating=summary.rating,
                airings=summary.airings + (airtime,),
            )
        shows[identifier] = summary

    return sorted(
        shows.values(),
        key=lambda show: (
            min(time or "99:99" for time in show.airings),
            show.name.casefold(),
        ),
    )


def build_output(
    schedule_date: date,
    schedule: Sequence[Mapping[str, object]],
    settings: AppSettings,
) -> ScheduleOutput:
    shows = summarize_shows(schedule)
    return {
        "date": schedule_date.isoformat(),
        "country": settings.schedule.country_code,
        "shows": [
            {
                "name": show.name,
                "airing_times": sorted({
                    time for time in show.airings if time is not None
                }),
                "genres": list(show.genres),
                "rating": show.rating,
            }
            for show in shows
        ],
        "source": settings.api.source_url,
    }


def parse_args(arguments: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fetch the configured TV schedule and save it as JSON."
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="write JSON to this file instead of the default OneDrive folder",
    )
    return parser.parse_args(arguments)


def default_output_path(
    settings: AppSettings,
    environment: Mapping[str, str] | None = None,
) -> Path:
    environment_values = os.environ if environment is None else environment
    for variable in settings.schedule.one_drive_environment_variables:
        sync_root = environment_values.get(variable)
        if sync_root:
            return (
                Path(sync_root)
                / settings.schedule.documents_folder
                / settings.schedule.output_folder
                / settings.schedule.output_filename
            )
    raise OSError(
        "OneDrive sync folder was not found. Set a OneDrive environment variable "
        "or pass --output with the synced folder path."
    )


def write_json(output_path: Path, data: Mapping[str, object]) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main(arguments: Sequence[str] | None = None) -> int:
    try:
        settings = load_settings()
    except (OSError, json.JSONDecodeError, ValueError) as error:
        print(f"Could not load TVMaze settings: {error}", file=sys.stderr)
        return 1

    try:
        logger = configure_logging(settings)
    except (OSError, ValueError) as error:
        print(f"Could not initialize application logging: {error}", file=sys.stderr)
        return 1

    logger.info("Starting daily schedule report")
    args = parse_args(arguments)
    schedule_date = date.today() + timedelta(days=settings.schedule.date_offset_days)
    try:
        schedule = fetch_schedule(schedule_date, settings)
        output = build_output(schedule_date, schedule, settings)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, ValueError) as error:
        logger.exception("Could not retrieve or process the TVMaze schedule")
        print(f"Could not load the TVMaze schedule: {error}", file=sys.stderr)
        return 1

    try:
        output_path = args.output or default_output_path(settings)
        write_json(output_path, output)
    except OSError as error:
        logger.exception("Could not write the TVMaze schedule report")
        print(f"Could not save the schedule JSON: {error}", file=sys.stderr)
        return 1

    logger.info("Saved daily schedule report to %s", output_path)
    print(f"Saved the TVMaze schedule to {output_path}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

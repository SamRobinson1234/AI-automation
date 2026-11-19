import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, timedelta
from pathlib import Path


API_URL = "https://api.tvmaze.com/schedule"
COUNTRY_CODE = "GB"
REQUEST_TIMEOUT_SECONDS = 20
USER_AGENT = "TVMazeScheduleSummary/1.0"
SOURCE_URL = "https://www.tvmaze.com/"
OUTPUT_FILENAME = "schedule.json"


def default_output_path():
    for variable in ("OneDriveCommercial", "OneDriveConsumer", "OneDrive"):
        sync_root = os.environ.get(variable)
        if sync_root:
            return Path(sync_root) / "Documents" / "TVMaze" / OUTPUT_FILENAME
    raise OSError(
        "OneDrive sync folder was not found. Set the OneDrive environment variable "
        "or pass --output with the synced folder path."
    )


def schedule_url(schedule_date):
    parameters = urllib.parse.urlencode({
        "country": COUNTRY_CODE,
        "date": schedule_date.isoformat(),
    })
    return f"{API_URL}?{parameters}"


def fetch_schedule(schedule_date):
    request = urllib.request.Request(schedule_url(schedule_date), headers={
        "User-Agent": USER_AGENT,
    })
    with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
        schedule = json.loads(response.read())

    if not isinstance(schedule, list):
        raise ValueError("TVMaze returned an unexpected schedule format")
    return schedule


def show_rating(show):
    rating = show.get("rating") or {}
    if not isinstance(rating, dict):
        raise ValueError("TVMaze returned an invalid show rating")
    return rating.get("average")


def show_genres(show):
    genres = show.get("genres") or []
    if not isinstance(genres, list) or not all(isinstance(genre, str) for genre in genres):
        raise ValueError("TVMaze returned invalid show genres")
    return genres


def summarize_shows(schedule):
    shows = {}
    for episode in schedule:
        if not isinstance(episode, dict) or not isinstance(episode.get("show"), dict):
            raise ValueError("TVMaze returned a schedule item without show details")

        show = episode["show"]
        show_id = show.get("id")
        name = show.get("name")
        if show_id is None or not isinstance(name, str):
            raise ValueError("TVMaze returned a show without an ID or name")

        summary = shows.get(show_id)
        if summary is None:
            summary = {
                "name": name,
                "genres": show_genres(show),
                "rating": show_rating(show),
                "airings": [],
            }
            shows[show_id] = summary
        summary["airings"].append({
            "time": episode.get("airtime"),
        })

    return sorted(
        shows.values(),
        key=lambda show: (
            min((airing["time"] or "99:99") for airing in show["airings"]),
            show["name"].casefold(),
        ),
    )


def build_output(schedule_date, schedule):
    shows = summarize_shows(schedule)
    return {
        "date": schedule_date.isoformat(),
        "country": COUNTRY_CODE,
        "shows": [
            {
                "name": show["name"],
                "airing_times": sorted({
                    airing["time"] for airing in show["airings"] if airing["time"]
                }),
                "genres": show["genres"],
                "rating": show["rating"],
            }
            for show in shows
        ],
        "source": SOURCE_URL,
    }


def parse_args(arguments=None):
    parser = argparse.ArgumentParser(
        description="Fetch tomorrow's UK TV schedule from TVMaze as JSON."
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="write JSON to this file instead of the default OneDrive folder",
    )
    return parser.parse_args(arguments)


def write_json(output_path, data):
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main(arguments=None):
    args = parse_args(arguments)
    schedule_date = date.today() + timedelta(days=1)
    try:
        output = build_output(schedule_date, fetch_schedule(schedule_date))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, ValueError) as error:
        print(f"Could not load the TVMaze schedule: {error}", file=sys.stderr)
        return 1

    try:
        output_path = args.output or default_output_path()
        write_json(output_path, output)
    except OSError as error:
        print(f"Could not save the schedule JSON: {error}", file=sys.stderr)
        return 1

    print(f"Saved tomorrow's TVMaze schedule to {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

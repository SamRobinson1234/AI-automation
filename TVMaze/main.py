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


def default_output_path():
    for variable in ("OneDriveCommercial", "OneDriveConsumer", "OneDrive"):
        sync_root = os.environ.get(variable)
        if sync_root:
            return Path(sync_root) / "Documents" / "TVMaze" / "schedule.json"
    raise OSError(
        "OneDrive sync folder was not found. Set the OneDrive environment variable "
        "or pass --output with the synced folder path."
    )


def fetch_schedule(schedule_date):
    query = urllib.parse.urlencode({
        "country": COUNTRY_CODE,
        "date": schedule_date.isoformat(),
    })
    request = urllib.request.Request(
        f"{API_URL}?{query}",
        headers={"User-Agent": "TVMazeScheduleSummary/1.0"},
    )
    with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
        schedule = json.loads(response.read())

    if not isinstance(schedule, list):
        raise ValueError("TVMaze returned an unexpected schedule format")
    return schedule


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

        summary = shows.setdefault(show_id, {
            "name": name,
            "genres": show.get("genres") or [],
            "rating": (show.get("rating") or {}).get("average"),
            "airings": [],
        })
        summary["airings"].append({
            "time": episode.get("airtime"),
            "name": episode.get("name"),
            "season": episode.get("season"),
            "number": episode.get("number"),
        })

    return sorted(
        shows.values(),
        key=lambda show: (
            min((airing["time"] or "99:99") for airing in show["airings"]),
            show["name"].casefold(),
        ),
    )


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


def main(arguments=None):
    args = parse_args(arguments)
    schedule_date = date.today() + timedelta(days=1)
    try:
        summaries = summarize_shows(fetch_schedule(schedule_date))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, ValueError) as error:
        print(f"Could not load the TVMaze schedule: {error}", file=sys.stderr)
        return 1

    shows = [{
        "name": show["name"],
        "airing_times": sorted({
            airing["time"] for airing in show["airings"] if airing["time"]
        }),
        "genres": show["genres"],
        "rating": show["rating"],
    } for show in summaries]
    output = {
        "date": schedule_date.isoformat(),
        "country": COUNTRY_CODE,
        "shows": shows,
        "source": "https://www.tvmaze.com/",
    }
    serialized_output = json.dumps(output, ensure_ascii=False, indent=2) + "\n"
    try:
        output_path = args.output or default_output_path()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(serialized_output, encoding="utf-8")
    except OSError as error:
        print(f"Could not save the schedule JSON: {error}", file=sys.stderr)
        return 1

    print(f"Saved tomorrow's TVMaze schedule to {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

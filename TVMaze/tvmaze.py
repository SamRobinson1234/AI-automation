import json
import math
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


SEARCH_URL = "https://api.tvmaze.com/search/shows"
REQUEST_TIMEOUT_SECONDS = 20
USER_AGENT = "TVMazeShowLookup/1.0"
CONFIG_FILE = Path(__file__).resolve().with_name("tvmaze_config.json")
DISPLAY_FIELDS = {
    "title": "Title",
    "genre": "Genres",
    "rating": "Rating",
    "premiere_date": "Premiere date",
}


def load_config():
    with CONFIG_FILE.open(encoding="utf-8") as config_file:
        config = json.load(config_file)

    if not isinstance(config, dict):
        raise ValueError("Configuration must be a JSON object")
    display = config.get("display")
    if not isinstance(display, dict) or set(display) != set(DISPLAY_FIELDS):
        raise ValueError(
            "Configuration 'display' must contain title, genre, rating, and premiere_date"
        )
    if not all(isinstance(enabled, bool) for enabled in display.values()):
        raise ValueError("Every configuration value in 'display' must be true or false")

    genre_filter = config.get("genre_filter")
    if not isinstance(genre_filter, list) or not all(
        isinstance(genre, str) and genre.strip() for genre in genre_filter
    ):
        raise ValueError("Configuration 'genre_filter' must be a list of genre names")

    minimum_rating = config.get("minimum_rating")
    if (
        isinstance(minimum_rating, bool)
        or not isinstance(minimum_rating, (int, float))
        or not math.isfinite(minimum_rating)
        or not 0 <= minimum_rating <= 10
    ):
        raise ValueError("Configuration 'minimum_rating' must be a number from 0 to 10")

    return {
        "display": display,
        "genre_filter": [genre.strip().casefold() for genre in genre_filter],
        "minimum_rating": minimum_rating,
    }


def search_url(show_name):
    return f"{SEARCH_URL}?{urllib.parse.urlencode({'q': show_name})}"


def find_show(show_name, genre_filter=None, minimum_rating=None):
    request = urllib.request.Request(
        search_url(show_name),
        headers={"User-Agent": USER_AGENT},
    )
    with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
        results = json.loads(response.read())

    if not isinstance(results, list):
        raise ValueError("TVMaze returned an unexpected search format")

    required_genres = {genre.casefold() for genre in (genre_filter or [])}
    for result in results:
        show = result.get("show") if isinstance(result, dict) else None
        if not isinstance(show, dict) or not isinstance(show.get("name"), str):
            raise ValueError("TVMaze returned invalid show details")

        genres = show.get("genres") or []
        rating = show.get("rating") or {}
        if not isinstance(genres, list) or not all(isinstance(item, str) for item in genres):
            raise ValueError("TVMaze returned invalid show genres")
        if not isinstance(rating, dict):
            raise ValueError("TVMaze returned an invalid show rating")
        average_rating = rating.get("average")
        if average_rating is not None and (
            isinstance(average_rating, bool)
            or not isinstance(average_rating, (int, float))
            or not math.isfinite(average_rating)
        ):
            raise ValueError("TVMaze returned an invalid rating value")
        if required_genres and not required_genres.intersection(
            genre.casefold() for genre in genres
        ):
            continue
        if minimum_rating is not None and (
            average_rating is None or average_rating <= minimum_rating
        ):
            continue

        return {
            "name": show["name"],
            "rating": average_rating,
            "genres": genres,
            "premiered": show.get("premiered"),
        }
    return None


def main():
    try:
        config = load_config()
    except (OSError, json.JSONDecodeError, ValueError) as error:
        print(f"Could not load {CONFIG_FILE.name}: {error}", file=sys.stderr)
        return 1

    show_name = input("Enter a TV show name: ").strip()
    if not show_name:
        print("Please enter a TV show name.", file=sys.stderr)
        return 1

    try:
        show = find_show(
            show_name,
            config["genre_filter"],
            config["minimum_rating"],
        )
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, ValueError) as error:
        print(f"Could not retrieve the TV show: {error}", file=sys.stderr)
        return 1

    if show is None:
        if config["genre_filter"]:
            genres = ", ".join(config["genre_filter"])
            print(
                f"No TV show found for {show_name!r} matching genre(s): {genres} "
                f"and rating above {config['minimum_rating']}."
            )
        else:
            print(
                f"No TV show found for {show_name!r} with a rating above "
                f"{config['minimum_rating']}."
            )
        return 1

    print("\nTVMaze show report")
    values = {
        "title": show["name"],
        "genre": ", ".join(show["genres"]) if show["genres"] else "Not listed",
        "rating": show["rating"] if show["rating"] is not None else "Not rated",
        "premiere_date": show["premiered"] or "Unknown",
    }
    for field, label in DISPLAY_FIELDS.items():
        if config["display"][field]:
            print(f"{label}: {values[field]}")
    print("Source: https://www.tvmaze.com/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

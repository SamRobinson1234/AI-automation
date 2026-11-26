"""Retrieve recent football results and team xG totals from BBC Sport."""

from __future__ import annotations

import json
import os
import re
import time
import traceback
from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, cast
from urllib.parse import urljoin
from urllib.request import Request, urlopen


SCRIPT_DIRECTORY = Path(__file__).resolve().parent
CONFIG_PATH = SCRIPT_DIRECTORY / "bbc_sport_config.json"
RUN_LOG_PATH = SCRIPT_DIRECTORY / "runlog"
DATE_PATTERN = re.compile(
    r"\b(\d{1,2})(?:st|nd|rd|th)?\s+"
    r"(January|February|March|April|May|June|July|August|September|October|November|December)\b",
    re.IGNORECASE,
)
RESULT_PATTERN = re.compile(
    r"(?P<home>.+?)\s+(?P<home_score>\d+)\s*,\s*"
    r"(?P<away>.+?)\s+(?P<away_score>\d+)\s+at\s+Full time",
    re.IGNORECASE,
)
XG_VALUE_PATTERN = re.compile(r"([0-9]+(?:\.[0-9]+)?)")


@dataclass(frozen=True)
class AppConfig:
    scores_fixtures_url_template: str
    league_slug: str
    max_months_to_search: int
    report_lookback_days: int
    request_timeout_seconds: int
    fetch_attempts: int
    retry_delay_seconds: int
    user_agent: str
    output_directory: Path
    output_file_prefix: str
    xg_section_label: str
    xg_stat_label: str


@dataclass(frozen=True)
class Match:
    match_date: str
    home_team: str
    home_score: int
    away_team: str
    away_score: int
    match_url: str
    home_xg: float | None = None
    away_xg: float | None = None


class _ResultsPageParser(HTMLParser):
    def __init__(self, year: int, month: int) -> None:
        super().__init__(convert_charrefs=True)
        self.year = year
        self.month = month
        self.current_date = ""
        self.matches: list[Match] = []
        self._heading_tag: str | None = None
        self._heading_parts: list[str] = []
        self._anchor_href: str | None = None
        self._anchor_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag in {"h1", "h2", "h3", "h4"}:
            self._heading_tag = tag
            self._heading_parts = []
        if tag == "a":
            href = attributes.get("href")
            if href is not None and "/sport/football/live/" in href:
                self._anchor_href = href
                self._anchor_parts = []

    def handle_endtag(self, tag: str) -> None:
        if tag == self._heading_tag:
            heading = " ".join(self._heading_parts)
            date_match = DATE_PATTERN.search(heading)
            if date_match is not None:
                day = int(date_match.group(1))
                month_name = date_match.group(2)
                parsed_date = datetime.strptime(
                    f"{day} {month_name} {self.year}", "%d %B %Y"
                ).date()
                if parsed_date.month == self.month:
                    self.current_date = parsed_date.isoformat()
            self._heading_tag = None
            self._heading_parts = []

        if tag == "a" and self._anchor_href is not None:
            self._finish_anchor()

    def handle_data(self, data: str) -> None:
        if self._heading_tag is not None:
            self._heading_parts.append(data)
        if self._anchor_href is not None:
            self._anchor_parts.append(data)

    def _finish_anchor(self) -> None:
        if self._anchor_href is None:
            return

        text = re.sub(r"\s+", " ", " ".join(self._anchor_parts)).strip()
        result = RESULT_PATTERN.search(text)
        if result is not None:
            self.matches.append(
                Match(
                    match_date=self.current_date,
                    home_team=result.group("home").strip(),
                    home_score=int(result.group("home_score")),
                    away_team=result.group("away").strip(),
                    away_score=int(result.group("away_score")),
                    match_url=urljoin(
                        "https://www.bbc.co.uk",
                        self._anchor_href.split("#", maxsplit=1)[0],
                    ),
                )
            )
        self._anchor_href = None
        self._anchor_parts = []


class _XGSectionParser(HTMLParser):
    def __init__(self, section_label: str) -> None:
        super().__init__(convert_charrefs=True)
        self.section_label = section_label
        self.text_parts: list[str] = []
        self._section_depth = 0
        self._capturing = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if self._capturing and tag == "section":
            self._section_depth += 1
        elif (
            not self._capturing
            and tag == "section"
            and attributes.get("aria-labelledby") == self.section_label
        ):
            self._capturing = True
            self._section_depth = 1

    def handle_endtag(self, tag: str) -> None:
        if self._capturing and tag == "section":
            self._section_depth -= 1
            if self._section_depth == 0:
                self._capturing = False

    def handle_data(self, data: str) -> None:
        if self._capturing and data.strip():
            self.text_parts.append(data.strip())


def parse_results_page(html: str, year: int, month: int) -> list[Match]:
    """Parse completed match cards from one BBC monthly results page."""
    parser = _ResultsPageParser(year, month)
    parser.feed(html)
    return parser.matches


def parse_team_xg(
    html: str,
    home_team: str,
    away_team: str,
    section_label: str = "advanced-match-stats-expected",
    stat_label: str = "xG",
) -> tuple[float | None, float | None]:
    """Extract the first team-level xG row from BBC's expected-goals section."""
    parser = _XGSectionParser(section_label)
    parser.feed(html)
    text_parts = parser.text_parts
    try:
        stat_index = next(
            index
            for index, text in enumerate(text_parts)
            if text.casefold() == stat_label.casefold()
        )
    except StopIteration:
        return None, None

    values: dict[str, float] = {}
    index = stat_index + 1
    while index < len(text_parts) and len(values) < 2:
        text = text_parts[index]
        for team in (home_team, away_team):
            team_pattern = re.compile(
                rf"{re.escape(team)}\s+([0-9]+(?:\.[0-9]+)?)",
                re.IGNORECASE,
            )
            combined_match = team_pattern.fullmatch(text)
            if combined_match is not None:
                values[team.casefold()] = float(combined_match.group(1))
                break

            if text.casefold() == team.casefold() and index + 1 < len(text_parts):
                number_match = XG_VALUE_PATTERN.fullmatch(text_parts[index + 1])
                if number_match is not None:
                    values[team.casefold()] = float(number_match.group(1))
                    index += 1
                    break
        index += 1

    return values.get(home_team.casefold()), values.get(away_team.casefold())


def filter_matches_to_last_days(
    matches: list[Match],
    as_of: date,
    lookback_days: int,
) -> list[Match]:
    """Keep completed matches dated within the inclusive rolling date window."""
    first_date = as_of - timedelta(days=lookback_days - 1)
    return [
        match
        for match in matches
        if first_date <= date.fromisoformat(match.match_date) <= as_of
    ]


def build_output_path(
    output_directory: Path,
    output_file_prefix: str,
    report_date: date,
) -> Path:
    """Build a unique, date-stamped path for a weekly JSON report."""
    return output_directory / f"{output_file_prefix}_{report_date.isoformat()}.json"


def _read_config(config_path: Path = CONFIG_PATH) -> AppConfig:
    with config_path.open("r", encoding="utf-8") as config_file:
        raw: Any = json.load(config_file)
    if not isinstance(raw, dict):
        raise ValueError("Configuration must be a JSON object")

    string_fields = (
        "scores_fixtures_url_template",
        "league_slug",
        "user_agent",
        "output_directory",
        "output_file_prefix",
        "xg_section_label",
        "xg_stat_label",
    )
    integer_fields = (
        "max_months_to_search",
        "report_lookback_days",
        "request_timeout_seconds",
        "fetch_attempts",
        "retry_delay_seconds",
    )
    for field in string_fields:
        if not isinstance(raw.get(field), str) or not raw[field].strip():
            raise ValueError(f"Configuration field '{field}' must be a non-empty string")
    for field in integer_fields:
        if not isinstance(raw.get(field), int) or isinstance(raw[field], bool) or raw[field] < 1:
            raise ValueError(f"Configuration field '{field}' must be a positive integer")

    output_directory = Path(os.path.expandvars(raw["output_directory"]))
    if "%" in str(output_directory):
        raise ValueError(
            "Could not resolve output_directory environment variable; "
            "check that OneDrive is configured"
        )

    return AppConfig(
        scores_fixtures_url_template=raw["scores_fixtures_url_template"],
        league_slug=raw["league_slug"],
        max_months_to_search=raw["max_months_to_search"],
        report_lookback_days=raw["report_lookback_days"],
        request_timeout_seconds=raw["request_timeout_seconds"],
        fetch_attempts=raw["fetch_attempts"],
        retry_delay_seconds=raw["retry_delay_seconds"],
        user_agent=raw["user_agent"],
        output_directory=output_directory,
        output_file_prefix=raw["output_file_prefix"],
        xg_section_label=raw["xg_section_label"],
        xg_stat_label=raw["xg_stat_label"],
    )


def _fetch_page(url: str, config: AppConfig) -> str:
    request = Request(url, headers={"User-Agent": config.user_agent})
    for attempt in range(config.fetch_attempts):
        try:
            with urlopen(request, timeout=config.request_timeout_seconds) as response:
                page_bytes = cast(bytes, response.read())
                return page_bytes.decode("utf-8", errors="replace")
        except (TimeoutError, OSError):
            if attempt + 1 == config.fetch_attempts:
                raise
            time.sleep(config.retry_delay_seconds)
    raise RuntimeError("BBC page fetch ended without a response")


def _month_offset(year: int, month: int, offset: int) -> tuple[int, int]:
    month_index = year * 12 + month - 1 - offset
    return month_index // 12, month_index % 12 + 1


def _scores_url(config: AppConfig, year: int, month: int) -> str:
    return config.scores_fixtures_url_template.format(
        league_slug=config.league_slug,
        year=year,
        month=month,
    )


def _collect_matches(config: AppConfig, as_of: date | None = None) -> list[Match]:
    report_date = as_of if as_of is not None else date.today()
    first_date = report_date - timedelta(days=config.report_lookback_days - 1)
    matches: list[Match] = []
    seen_urls: set[str] = set()
    reached_start_month = False

    for offset in range(config.max_months_to_search):
        year, month = _month_offset(report_date.year, report_date.month, offset)
        month_start = date(year, month, 1)
        if month_start < date(first_date.year, first_date.month, 1):
            reached_start_month = True
            break
        url = _scores_url(config, year, month)
        page_matches = parse_results_page(_fetch_page(url, config), year, month)
        for match in page_matches:
            if (
                match.match_url not in seen_urls
                and first_date <= date.fromisoformat(match.match_date) <= report_date
            ):
                matches.append(match)
                seen_urls.add(match.match_url)
        if (year, month) == (first_date.year, first_date.month):
            reached_start_month = True
            break

    if not reached_start_month:
        raise ValueError(
            "max_months_to_search is too small to cover the configured report window"
        )
    return sorted(matches, key=lambda match: match.match_date, reverse=True)


def _retrieve_match_xg(matches: list[Match], config: AppConfig) -> list[Match]:
    updated_matches: list[Match] = []
    for match in matches:
        page = _fetch_page(match.match_url, config)
        home_xg, away_xg = parse_team_xg(
            page,
            match.home_team,
            match.away_team,
            config.xg_section_label,
            config.xg_stat_label,
        )
        updated_matches.append(
            replace(match, home_xg=home_xg, away_xg=away_xg)
        )
    return updated_matches


def _rounded_xg(value: float | None) -> float | None:
    if value is None:
        return None
    return float(Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def _write_json(matches: list[Match], output_path: Path) -> None:
    records: list[dict[str, str | int | float | None]] = []
    for match in matches:
        records.append(
            {
                "match_date": match.match_date,
                "home_team": match.home_team,
                "home_score": match.home_score,
                "home_xg": _rounded_xg(match.home_xg),
                "away_team": match.away_team,
                "away_score": match.away_score,
                "away_xg": _rounded_xg(match.away_xg),
                "bbc_url": match.match_url,
            }
        )
    with output_path.open("w", encoding="utf-8") as json_file:
        json.dump(records, json_file, indent=2)
        json_file.write("\n")


def _append_run_log(message: str, log_path: Path) -> None:
    timestamp = datetime.now().astimezone().isoformat(timespec="seconds")
    with log_path.open("a", encoding="utf-8") as log_file:
        log_file.write(f"[{timestamp}] {message}\n")


def _run_report() -> tuple[Path, int]:
    config = _read_config()
    report_date = date.today()
    matches = _collect_matches(config, report_date)
    matches_with_xg = _retrieve_match_xg(matches, config)
    config.output_directory.mkdir(parents=True, exist_ok=True)
    output_path = build_output_path(
        config.output_directory,
        config.output_file_prefix,
        report_date,
    )
    _write_json(matches_with_xg, output_path)
    return output_path, len(matches_with_xg)


def main(log_path: Path = RUN_LOG_PATH) -> None:
    _append_run_log("Run started", log_path)
    try:
        output_path, match_count = _run_report()
    except Exception as error:
        _append_run_log(
            f"Run failed: {type(error).__name__}: {error}\n{traceback.format_exc()}",
            log_path,
        )
        raise

    _append_run_log(
        f"Run completed: {match_count} matches; JSON output: {output_path}",
        log_path,
    )
    print(f"Wrote {match_count} matches to {output_path}")


if __name__ == "__main__":
    main()

import importlib.util
import json
import sys
import tempfile
import unittest
from datetime import date
from io import BytesIO
from pathlib import Path
from unittest.mock import patch


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "BBC Sport data retrieval.py"
SPEC = importlib.util.spec_from_file_location("bbc_sport_data_retrieval", SCRIPT_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("Could not load BBC Sport data retrieval script for tests")
BBC_SPORT = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = BBC_SPORT
SPEC.loader.exec_module(BBC_SPORT)


class BBCSportDataTests(unittest.TestCase):
    def test_scores_url_uses_selected_league_from_config(self) -> None:
        config = BBC_SPORT.AppConfig(
            scores_fixtures_url_template=(
                "https://www.bbc.co.uk/sport/football/{league_slug}/"
                "scores-fixtures/{year:04d}-{month:02d}?filter=results"
            ),
            league_slug="championship",
            max_months_to_search=2,
            report_lookback_days=7,
            request_timeout_seconds=10,
            fetch_attempts=2,
            retry_delay_seconds=0,
            user_agent="test",
            output_directory=Path("."),
            output_file_prefix="report",
            xg_section_label="expected",
            xg_stat_label="xG",
        )

        url = BBC_SPORT._scores_url(config, 2026, 11)

        self.assertEqual(
            url,
            "https://www.bbc.co.uk/sport/football/championship/"
            "scores-fixtures/2026-11?filter=results",
        )

    def test_completed_results_page_extracts_match_score_date_and_url(self) -> None:
        page = """
        <h2>Monday 23rd November</h2>
        <a href="/sport/football/live/c64gnwyv7kvjt">
          <span class="visually-hidden">
            Brentford 4 , Everton 0 at Full time
          </span>
          Brentford Everton Full time
        </a>
        """

        matches = BBC_SPORT.parse_results_page(page, 2026, 11)

        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0].match_date, "2026-11-23")
        self.assertEqual(matches[0].home_team, "Brentford")
        self.assertEqual(matches[0].home_score, 4)
        self.assertEqual(matches[0].away_team, "Everton")
        self.assertEqual(matches[0].away_score, 0)
        self.assertEqual(
            matches[0].match_url,
            "https://www.bbc.co.uk/sport/football/live/c64gnwyv7kvjt",
        )

    def test_match_stats_extracts_team_totals_not_individual_player_xg(self) -> None:
        page = """
        <section aria-labelledby="advanced-match-stats-expected">
          <h3>Expected</h3>
          <h4>xG</h4>
          <span>Brentford 2.7673</span>
          <span>Everton 0.235</span>
          <h4>xG from open play</h4>
          <span>Brentford 1.3538</span>
          <span>Everton 0.1955</span>
        </section>
        <script>
          {"teamName":"Brentford","stats":[{"rowLabel":"Expected goals (xG)","statValue":"0.74"}]}
        </script>
        """

        home_xg, away_xg = BBC_SPORT.parse_team_xg(page, "Brentford", "Everton")

        self.assertEqual(home_xg, 2.7673)
        self.assertEqual(away_xg, 0.235)

    def test_missing_team_xg_is_reported_as_empty_values(self) -> None:
        home_xg, away_xg = BBC_SPORT.parse_team_xg(
            "<section aria-labelledby='advanced-match-stats-expected'></section>",
            "Arsenal",
            "Chelsea",
        )

        self.assertIsNone(home_xg)
        self.assertIsNone(away_xg)

    def test_json_rounds_xg_to_two_decimals_and_uses_null_when_missing(self) -> None:
        match = BBC_SPORT.Match(
            match_date="2026-11-23",
            home_team="Arsenal",
            home_score=2,
            away_team="Chelsea",
            away_score=1,
            match_url="https://www.bbc.co.uk/sport/football/live/example",
            home_xg=2.7673,
            away_xg=0.235,
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "report.json"

            BBC_SPORT._write_json([match], output_path)

            data = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual(
                data,
                [
                    {
                        "match_date": "2026-11-23",
                        "home_team": "Arsenal",
                        "home_score": 2,
                        "home_xg": 2.77,
                        "away_team": "Chelsea",
                        "away_score": 1,
                        "away_xg": 0.24,
                        "bbc_url": "https://www.bbc.co.uk/sport/football/live/example",
                    }
                ],
            )

    def test_only_matches_in_the_last_seven_days_are_kept(self) -> None:
        recent_match = BBC_SPORT.Match(
            "2026-11-25", "Arsenal", 2, "Chelsea", 1, "https://example.com/recent"
        )
        boundary_match = BBC_SPORT.Match(
            "2026-11-20", "Arsenal", 2, "Chelsea", 1, "https://example.com/boundary"
        )
        old_match = BBC_SPORT.Match(
            "2026-11-19", "Arsenal", 2, "Chelsea", 1, "https://example.com/old"
        )

        matches = BBC_SPORT.filter_matches_to_last_days(
            [recent_match, boundary_match, old_match],
            date(2026, 11, 26),
            7,
        )

        self.assertEqual(
            [match.match_url for match in matches],
            ["https://example.com/recent", "https://example.com/boundary"],
        )

    def test_report_path_includes_run_date(self) -> None:
        path = BBC_SPORT.build_output_path(
            Path("C:/OneDrive/Football auto"),
            "premier_league_results",
            date(2026, 11, 26),
        )

        self.assertEqual(
            path.name,
            "premier_league_results_2026-11-26.json",
        )

    def test_fetch_retries_after_a_timeout(self) -> None:
        config = BBC_SPORT.AppConfig(
            scores_fixtures_url_template="https://example.com/{year}-{month}",
            league_slug="premier-league",
            max_months_to_search=2,
            report_lookback_days=7,
            request_timeout_seconds=10,
            fetch_attempts=2,
            retry_delay_seconds=0,
            user_agent="test",
            output_directory=Path("."),
            output_file_prefix="report",
            xg_section_label="expected",
            xg_stat_label="xG",
        )
        response = BytesIO(b"ok")
        with (
            patch.object(BBC_SPORT, "urlopen", side_effect=[TimeoutError(), response]),
            patch.object(BBC_SPORT.time, "sleep") as sleep,
        ):
            result = BBC_SPORT._fetch_page("https://example.com", config)

        self.assertEqual(result, "ok")
        sleep.assert_called_once_with(0)

    def test_fetch_raises_after_all_retries_are_exhausted(self) -> None:
        config = BBC_SPORT.AppConfig(
            scores_fixtures_url_template="https://example.com/{year}-{month}",
            league_slug="premier-league",
            max_months_to_search=2,
            report_lookback_days=7,
            request_timeout_seconds=10,
            fetch_attempts=2,
            retry_delay_seconds=0,
            user_agent="test",
            output_directory=Path("."),
            output_file_prefix="report",
            xg_section_label="expected",
            xg_stat_label="xG",
        )
        with patch.object(BBC_SPORT, "urlopen", side_effect=TimeoutError("timeout")):
            with self.assertRaisesRegex(TimeoutError, "timeout"):
                BBC_SPORT._fetch_page("https://example.com", config)

    def test_main_appends_each_successful_run_to_log(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            log_path = Path(temp_dir) / "runlog"
            report_path = Path(temp_dir) / "report.json"
            with patch.object(BBC_SPORT, "_run_report", return_value=(report_path, 3)):
                BBC_SPORT.main(log_path)
                BBC_SPORT.main(log_path)

            log_contents = log_path.read_text(encoding="utf-8")
            self.assertEqual(log_contents.count("Run started"), 2)
            self.assertEqual(log_contents.count("Run completed"), 2)
            self.assertIn("3 matches", log_contents)
            self.assertIn(str(report_path), log_contents)

    def test_main_logs_failure_and_reraises_the_error(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            log_path = Path(temp_dir) / "runlog"
            with patch.object(
                BBC_SPORT,
                "_run_report",
                side_effect=TimeoutError("BBC request timed out"),
            ):
                with self.assertRaisesRegex(TimeoutError, "BBC request timed out"):
                    BBC_SPORT.main(log_path)

            log_contents = log_path.read_text(encoding="utf-8")
            self.assertIn("Run started", log_contents)
            self.assertIn("Run failed", log_contents)
            self.assertIn("BBC request timed out", log_contents)


if __name__ == "__main__":
    unittest.main()

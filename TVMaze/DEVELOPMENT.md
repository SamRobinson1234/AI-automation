# TVMaze developer guide

## What the files do

- `tvmaze.py` searches for shows and applies the filters.
- `tvmaze_web.py` runs the local website using Python.
- `tvmaze_search.html` controls the webpage's layout and appearance.
- `main.py` downloads the daily TV schedule and saves it as JSON.
- `app_settings.json` contains application settings, such as URLs and the log filename.
- `tvmaze_config.json` controls which details appear and filters by genre and rating.
- `runlog` records when the apps run, searches, and errors.
- `tests/` contains automated checks for the apps.

## Make common changes

- To hide or show report details, change the `display` values in `tvmaze_config.json`.
- To filter by genre, add a genre to `genre_filter`, such as `["Comedy"]`.
- To change the rating limit, edit `minimum_rating`. Shows must rate higher than this number.
- To change an app setting, edit `app_settings.json` rather than hard-coding it in Python.
- To change how the webpage looks, edit `tvmaze_search.html`.
- To change how searches or the schedule work, edit `tvmaze.py` or `main.py`.

## Use another TV guide

- Check that the other guide offers an API you are allowed to use.
- Write a failing test with an example response before changing the code.
- Change the API settings in `app_settings.json`.
- Update `tvmaze.py` to convert the new guide's show data into the app's show format.
- Update `main.py` too if the schedule data has a different format.
- Keep error handling for missing ratings, genres, dates, and unavailable data.
- Update the README if users need different setup steps or attribution.
- Never put passwords or private API keys in the webpage or source control.

## Check changes

- Open the `TVMaze` folder in VS Code to see strict Pylance type warnings.
- Install the type checker with `python -m pip install -r requirements-dev.txt`.
- Run `python -m unittest discover -s tests -v`.
- Run `python -m mypy`.
- Fix all test and type-check errors before merging. GitHub Actions runs these checks too.

# TVMaze UK Daily TV Schedule

This command-line script fetches the next day's UK TV schedule from the free TVMaze API and saves a JSON file in the local OneDrive-synced `Documents\TVMaze` folder. It includes the date, country code, source, and each scheduled show once, with airing times, genres, and TVMaze rating. Missing ratings are JSON `null`; missing genres are an empty array. The schedule date is calculated at runtime, so the script always requests tomorrow.

## Look up a TV show

Run `python tvmaze.py` in this directory and enter a show name when prompted. The script searches TVMaze and displays the first matching show, including its rating, genres, and premiere date. An unrated show, missing genres, or unknown premiere date is shown clearly. The lookup uses the free TVMaze API and requires an internet connection.

Edit `tvmaze_config.json` to control the report without changing the script. Set `display.title`, `display.genre`, `display.rating`, or `display.premiere_date` to `true` or `false` to show or hide each field. Set `genre_filter` to an empty list to accept any genre, or add one or more genre names (for example, `["Drama"]`) to select results matching any of those genres. Genre matching ignores capitalization. Set `minimum_rating` to a number from 0 to 10 to only return shows rated strictly above that number; with the default of `8`, unrated shows and shows rated exactly 8 are excluded.

Application defaults such as API endpoints, request timeouts, user-agent strings, web-server settings, schedule output location, and report labels are in `app_settings.json`.
Application startup, search, schedule, and error events are recorded in the `runlog` file in this folder.

## Search from a webpage

Run `python tvmaze_web.py` in this directory. It starts the search page at `http://127.0.0.1:8765/` and opens it in your browser. Enter a show name and select **Search** to view the information returned by TVMaze. The search form and result rendering run on the Python server; the page does not need JavaScript. The existing display and genre settings in `tvmaze_config.json` apply to web searches too. Keep the terminal window open while using the page; press Ctrl+C in that window to stop the local server. Python and an internet connection are required.

## Run

1. Make sure Python 3 and an internet connection are available.
2. Open a terminal in this directory.
3. Run `python main.py`. The script saves or updates `schedule.json` in `%OneDrive%\Documents\TVMaze`.

The output location is based on the `OneDriveCommercial`, `OneDriveConsumer`, or `OneDrive` environment variable. Use `python main.py --output "C:\path\to\synced\TVMaze\schedule.json"` to choose another file. The script creates the destination folder if needed and writes UTF-8 JSON.

## Trigger a Power Automate cloud flow daily

1. In Windows Task Scheduler, create a daily task. Set its program to your Python executable, its arguments to `"<path-to-this-folder>\main.py"`, and **Start in** to this project folder. The script will save to the synced OneDrive `Documents\TVMaze` folder automatically.
2. In Power Automate, create an automated cloud flow with the OneDrive trigger **When a file is created or modified (properties only)**. Select the `TVMaze` folder. The fixed `schedule.json` filename is updated each day, so use a trigger that includes modifications.
3. Add **Get file content** using the file identifier from the trigger, then **Parse JSON** using that content. The top-level properties are `date`, `country`, `shows`, and `source`; each show has `name`, `airing_times`, `genres`, and `rating`.

The Windows task runs the Python script; OneDrive sync carries the file to the cloud, where the flow triggers. Choose a run time that leaves enough time for OneDrive to sync before the flow needs the file. The schedule date is tomorrow relative to the computer's local date.

## Development checks

Open the `TVMaze` folder in VS Code to apply Pylance strict type checking. Run `python -m unittest discover -s tests -v` and `python -m mypy` before committing. Install the type checker with `python -m pip install -r requirements-dev.txt`. The GitHub Actions workflow runs both checks for changes in this folder.

See [DEVELOPMENT.md](DEVELOPMENT.md) for the application flow, configuration guide, and steps for adapting the app to another TV guide provider.

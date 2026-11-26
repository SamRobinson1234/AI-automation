# BBC Sport weekly football report

- The script gets completed results for the configured league from the last seven calendar days.
- It visits each match page and collects the home and away teams' total xG.
- Player-level xG is not included. Missing team xG values are `null`.
- xG is rounded to two decimal places, as displayed by BBC Sport.
- The report is saved as a date-stamped JSON file in `OneDrive\Documents\Football auto`.
- Temporary BBC connection and timeout failures are retried up to three times.
- Every run is appended to the `runlog` file in this folder, including its start, result path, match count, or error details.
- Run it from the project folder with:

  ```powershell
  .\.venv\Scripts\python.exe "Football auto\BBC Sport data retrieval.py"
  ```

- Edit `league_slug` in `bbc_sport_config.json` to choose another BBC Sport competition. Use the competition's BBC URL slug, such as `premier-league` or `championship`.
- BBC coverage and match xG availability differ by competition; matches without team xG are recorded with `null` values.
- Edit the other settings in `bbc_sport_config.json` to change the report period, OneDrive folder, filename prefix, or retry settings.
- To install the Tuesday 9:00 AM scheduled task, run this from PowerShell:

  ```powershell
  powershell.exe -ExecutionPolicy Bypass -File "Football auto\setup_weekly_task.ps1"
  ```

- The task runs as the current Windows user, so that user must be signed in for OneDrive access.
- If the computer is asleep at 9:00 AM, the task is set to wake it and run when available.

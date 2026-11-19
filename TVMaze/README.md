# TVMaze UK Daily TV Schedule

This command-line script fetches the next day's UK TV schedule from the free TVMaze API and saves a JSON file in the local OneDrive-synced `Documents\TVMaze` folder. It includes the date, country code, source, and each scheduled show once, with airing times, genres, and TVMaze rating. Missing ratings are JSON `null`; missing genres are an empty array. The schedule date is calculated at runtime, so the script always requests tomorrow.

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

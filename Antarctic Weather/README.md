# Antarctic Weather

A small local dashboard for hourly temperatures, wind speeds, and playful penguin suggestions in four Antarctic regions. Choose North, East, South, or West Antarctica, then select a travel date and hour in that location's local time. Each region uses a named representative station: Esperanza Base, Davis Station, Amundsen–Scott South Pole Station, or Rothera Research Station. The forecast rolls forward to cover the next 168 hours and refreshes once an hour while the dashboard is open; the server caches each region's response for 55 minutes to reduce repeated API requests.

## Journey planner

Choose a start station, end station, and departure time, then enter the journey's waddling and swimming distances. The planner estimates duration using editable speeds, initially 2.5 km/h waddling and 8 km/h swimming, and displays a suggestion for each journey hour. A straight-line distance between stations is shown for reference; entered segment distances determine the estimate and can differ from it. Journey weather and suggestions use the start station's forecast only, not weather along the route. The forecast covers at most seven days, and uncovered journey hours are marked unavailable rather than extrapolated.

## Run

1. Make sure Python 3 is installed and the computer is connected to the internet.
2. Open a terminal in this directory.
3. Run `python main.py`.
4. The dashboard opens at <http://127.0.0.1:8765>.

Keep the terminal window open while viewing the dashboard; press Ctrl+C there to stop it. The app requests current forecast data from [Open-Meteo](https://open-meteo.com/). It does not need an API key. The **Local vibes** illustration is drawn as an inline SVG and changes to match the selected temperature and wind conditions.

When wind exceeds 10 mph, below-zero temperatures recommend a huddle, while above-zero temperatures recommend suncream and warn against umbrellas. At 10 mph or less, below zero recommends a coat and above zero recommends hitting the beach. Exactly zero degrees gets a neutral message. These suggestions are only playful: penguins are adapted to their environment, and people should not dress, handle, or apply products to wild penguins.

from flask import Flask, render_template_string
from datetime import datetime, timedelta
import requests

app = Flask(__name__)

# Simple cache for API responses
cache = {
    'weather': {'data': None, 'timestamp': None},
    'electricity': {'data': None, 'timestamp': None},
    'cheapest': {'data': None, 'timestamp': None}
}
CACHE_TTL = 300  # 5 minutes in seconds


def get_cached(key, fetch_func):
    """Return cached data if fresh, otherwise fetch and cache."""
    now = datetime.now()
    if cache[key]['data'] and cache[key]['timestamp']:
        age = (now - cache[key]['timestamp']).total_seconds()
        if age < CACHE_TTL:
            app.logger.info(f"Using cached {key} (age: {int(age)}s)")
            return cache[key]['data']

    data = fetch_func()
    cache[key]['data'] = data
    cache[key]['timestamp'] = now
    return data

# Tampere Coordinates
LAT = "61.4991"
LON = "23.7871"
NYSSE_URL = "https://lissu.tampere.fi/timetable/rest/stopdisplays/0870"
ELECTRICITY_URL = "https://api.spot-hinta.fi/JustNow"
CHEAPEST_URL = "https://www.sahkohinta-api.fi/api/v1/halpa?tunnit=2&tulos=sarja"

HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <meta http-equiv="refresh" content="60">
    <style>
        body { font-family: sans-serif; text-align: center; background: white; padding: 20px; }
        .temp { font-size: 80px; font-weight: bold; }
        .info { font-size: 24px; color: #555; margin-bottom: 40px; }
        .tram { font-size: 50px; border: 3px solid black; margin: 10px; padding: 10px; }
    </style>
</head>
<body>
    <div class="temp">{{ temp }}°C</div>
    <div class="info">Tuntuu: {{ feels }}°C | Tuuli: {{ wind }} m/s</div>
    <hr>
    {% for tram in trams %}
        <div class="tram">RATIKKA {{ tram.line }}: {{ tram.mins }} min</div>
    {% endfor %}
    <hr>
    <div class="info">Sähkö nyt</div>
    <div class="temp">{{ electricity }} c/kWh</div>
    <div class="temp" style="margin-top: 20px;">{{ cheap_period }}</div>
</body>
</html>
"""

@app.route('/')
def home():
    # 1. Get Weather (cached)
    def fetch_weather():
        w_url = f"https://api.open-meteo.com/v1/forecast?latitude={LAT}&longitude={LON}&current=temperature_2m,apparent_temperature,wind_speed_10m&wind_speed_unit=ms"
        return requests.get(w_url, timeout=10).json()['current']

    weather_data = get_cached('weather', fetch_weather)

    # 2. Get Trams
    try:
        t_res = requests.get(NYSSE_URL, timeout=10)
        t_data = t_res.json()
        
        trams = []
        # We navigate straight to the list of arrival times
        # nextStopVisits[0] -> stopVisits
        if 'nextStopVisits' in t_data and t_data['nextStopVisits']:
            stop_visits = t_data['nextStopVisits'][0].get('stopVisits', [])
            
            for v in stop_visits[:2]:
                # Get the minutes, default to '?' if something is weird
                m = v.get('estimatedMinutesUntilDeparture', '?')
                trams.append({'mins': m})
        
        if not trams:
            trams = [{'mins': 'Ei vuoroja'}]

    except Exception as e:
        app.logger.error(f"Quick Fetch Error: {e}")
        trams = [{'mins': 'Error'}]

    # 3. Get Electricity Price (cached)
    def fetch_electricity():
        res = requests.get(ELECTRICITY_URL, timeout=10)
        return res.json()

    try:
        e_data = get_cached('electricity', fetch_electricity)
        electricity = f"{e_data['PriceWithTax'] * 100:.1f}"
    except Exception as e:
        app.logger.error(f"Electricity Fetch Error: {e}")
        electricity = "?"

    # 4. Get Cheapest 2-hour period in next 12 hours (cached)
    def fetch_cheapest():
        now = datetime.now()
        end_time = now + timedelta(hours=12)
        aikaraja = f"{now.strftime('%Y-%m-%dT%H:00')}_{end_time.strftime('%Y-%m-%dT%H:00')}"
        res = requests.get(f"{CHEAPEST_URL}&aikaraja={aikaraja}", timeout=10)
        return res.json()

    try:
        c_data = get_cached('cheapest', fetch_cheapest)
        now = datetime.now()

        start_hour = int(c_data[0]['aikaleima_suomi'].split('T')[1].split(':')[0])
        end_hour = (int(c_data[-1]['aikaleima_suomi'].split('T')[1].split(':')[0]) + 1) % 24
        avg_price = sum(h['hinta'] for h in c_data) / len(c_data)

        # Check if we're currently in the cheap period
        current_hour = now.hour
        in_cheap_period = False
        if start_hour < end_hour:
            in_cheap_period = start_hour <= current_hour < end_hour
        else:  # Wraps around midnight
            in_cheap_period = current_hour >= start_hour or current_hour < end_hour

        cheap_period = f"Halvin 2h: {start_hour:02d}-{end_hour:02d} ({avg_price:.1f} c)"
        if in_cheap_period:
            cheap_period += " nyt!"
    except Exception as e:
        app.logger.error(f"Cheapest Period Fetch Error: {e}")
        cheap_period = ""

    return render_template_string(HTML_TEMPLATE,
        temp=round(weather_data['temperature_2m']),
        feels=round(weather_data['apparent_temperature']),
        wind=round(weather_data['wind_speed_10m']),
        trams=trams,
        electricity=electricity,
        cheap_period=cheap_period
    )
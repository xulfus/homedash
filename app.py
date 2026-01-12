from flask import Flask, render_template_string
import requests

app = Flask(__name__)

# Tampere Coordinates
LAT = "61.4991"
LON = "23.7871"
NYSSE_URL = "https://lissu.tampere.fi/timetable/rest/stopdisplays/0870"
ELECTRICITY_URL = "https://api.spot-hinta.fi/JustNow"

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
    <div class="info">Lentävänniemi A</div>
    {% for tram in trams %}
        <div class="tram">RATIKKA {{ tram.line }}: {{ tram.mins }} min</div>
    {% endfor %}
    <hr>
    <div class="info">Sähkö nyt</div>
    <div class="temp">{{ electricity }} c/kWh</div>
</body>
</html>
"""

@app.route('/')
def home():
    # 1. Get Weather
    w_url = f"https://api.open-meteo.com/v1/forecast?latitude={LAT}&longitude={LON}&current=temperature_2m,apparent_temperature,wind_speed_10m&wind_speed_unit=ms"
    weather_data = requests.get(w_url).json()['current']

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

    # 3. Get Electricity Price
    try:
        e_res = requests.get(ELECTRICITY_URL, timeout=10)
        e_data = e_res.json()
        electricity = f"{e_data['PriceWithTax'] * 100:.1f}"
    except Exception as e:
        app.logger.error(f"Electricity Fetch Error: {e}")
        electricity = "?"

    return render_template_string(HTML_TEMPLATE,
        temp=round(weather_data['temperature_2m']),
        feels=round(weather_data['apparent_temperature']),
        wind=round(weather_data['wind_speed_10m']),
        trams=trams,
        electricity=electricity
    )
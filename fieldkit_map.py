import folium
import json
import time
import threading
import webbrowser
import os
from datetime import datetime

MAP_FILE = os.path.expanduser("~/fieldkit_map.html")

def generate_map(data):
    lat = data["gps"]["lat"]
    lon = data["gps"]["lon"]

    m = folium.Map(
        location=[lat, lon],
        zoom_start=13,
        tiles="CartoDB dark_matter"
    )

    folium.Marker(
        [lat, lon],
        popup="FIELDKIT POSITION",
        icon=folium.Icon(color="green", icon="crosshairs", prefix="fa"),
        tooltip="YOU"
    ).add_to(m)

    folium.Circle(
        [lat, lon],
        radius=500, color="#00ff41",
        fill=True, fill_opacity=0.05,
        tooltip="500m"
    ).add_to(m)
    folium.Circle(
        [lat, lon],
        radius=2000, color="#00ff41",
        fill=True, fill_opacity=0.02,
        tooltip="2km"
    ).add_to(m)

    for aircraft in data.get("aircraft", []):
        if aircraft.get("lat") and aircraft.get("lon"):
            folium.Marker(
                [aircraft["lat"], aircraft["lon"]],
                popup=f"{aircraft['callsign']}<br>{aircraft['alt']}ft<br>{aircraft['speed']}kts",
                icon=folium.Icon(color="blue", icon="plane", prefix="fa"),
                tooltip=aircraft["callsign"]
            ).add_to(m)

    for drone in data.get("drones", []):
        if drone.get("lat") and drone.get("lon"):
            color = "red" if drone["threat"] == "HIGH" else "orange" if drone["threat"] == "MEDIUM" else "gray"
            folium.Marker(
                [drone["lat"], drone["lon"]],
                popup=f"{drone['id']}<br>{drone['model']}<br>THREAT:{drone['threat']}<br>{drone['method']}",
                icon=folium.Icon(color=color, icon="warning-sign", prefix="glyphicon"),
                tooltip=f"DRONE {drone['threat']}"
            ).add_to(m)
            if drone.get("operator_lat") and drone.get("operator_lon"):
                folium.PolyLine(
                    [[drone["lat"], drone["lon"]],
                     [drone["operator_lat"], drone["operator_lon"]]],
                    color="orange", weight=1, opacity=0.5,
                    tooltip="drone->operator"
                ).add_to(m)

    for net in data.get("wifi", []):
        folium.CircleMarker(
            [lat + 0.001 * hash(net["ssid"]) % 10 * 0.001,
             lon + 0.001 * hash(net["bssid"]) % 10 * 0.001],
            radius=8,
            color="red" if net["enc"] == "OPEN" else "#00ff41",
            fill=True, fill_opacity=0.6,
            popup=f"{net['ssid']}<br>{net['enc']}<br>{net['signal']}dBm",
            tooltip=net["ssid"]
        ).add_to(m)

    title = f"""
    <div style="position:fixed;top:10px;left:50%;transform:translateX(-50%);
    background:#0a0f0a;color:#00ff41;padding:8px 16px;
    font-family:monospace;font-size:13px;border:1px solid #00ff41;z-index:9999;">
    FIELDKIT MAP  //  {datetime.now().strftime('%H:%M:%S')}  //
    AC:{len(data.get('aircraft',[]))}  DRONES:{len(data.get('drones',[]))}  WIFI:{len(data.get('wifi',[]))}
    </div>"""
    m.get_root().html.add_child(folium.Element(title))

    m.save(MAP_FILE)

def build_data_payload(fk_data):
    return {
        "gps": {
            "lat": fk_data.gps.lat,
            "lon": fk_data.gps.lon,
            "alt": fk_data.gps.alt
        },
        "aircraft": fk_data.sdr.aircraft,
        "drones": fk_data.drone.drones,
        "wifi": fk_data.wifi.networks
    }

def start_map_server(fk_data):
    def loop():
        while True:
            try:
                payload = build_data_payload(fk_data)
                generate_map(payload)
            except Exception as e:
                pass
            time.sleep(5)
    t = threading.Thread(target=loop, daemon=True)
    t.start()
    time.sleep(1)
    webbrowser.open(f"file://{MAP_FILE}")
    print(f"Map running at {MAP_FILE}")

if __name__ == "__main__":
    import sys
    sys.path.insert(0, os.path.expanduser("~"))
    from fieldkit_data import FieldKitData
    data = FieldKitData()
    print("Generating map...")
    for _ in range(5):
        data.update()
    payload = build_data_payload(data)
    generate_map(payload)
    webbrowser.open(f"file://{MAP_FILE}")
    print(f"Map saved to {MAP_FILE}")
    print("Auto-updating every 5 seconds. Press Ctrl+C to stop.")
    while True:
        data.update()
        payload = build_data_payload(data)
        generate_map(payload)
        time.sleep(5)

import sqlite3
import random
import time
from datetime import datetime

DB_PATH = "fieldkit.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS gps_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT, lat REAL, lon REAL, alt REAL, speed REAL)""")
    c.execute("""CREATE TABLE IF NOT EXISTS wifi_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT, ssid TEXT, bssid TEXT, signal INTEGER,
        encryption TEXT, channel INTEGER, lat REAL, lon REAL)""")
    c.execute("""CREATE TABLE IF NOT EXISTS aircraft_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT, callsign TEXT, icao TEXT, alt INTEGER,
        speed INTEGER, heading INTEGER, lat REAL, lon REAL, distance REAL)""")
    c.execute("""CREATE TABLE IF NOT EXISTS sdr_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT, frequency REAL, signal_db REAL,
        device_type TEXT, lat REAL, lon REAL)""")
    c.execute("""CREATE TABLE IF NOT EXISTS lora_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT, node_id TEXT, message TEXT,
        rssi INTEGER, lat REAL, lon REAL)""")
    c.execute("""CREATE TABLE IF NOT EXISTS pentest_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT, ssid TEXT, bssid TEXT, event TEXT,
        lat REAL, lon REAL)""")
    c.execute("""CREATE TABLE IF NOT EXISTS drone_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT, drone_id TEXT, model TEXT,
        lat REAL, lon REAL, alt REAL, speed REAL,
        operator_lat REAL, operator_lon REAL,
        detection_method TEXT, threat_level TEXT,
        device_lat REAL, device_lon REAL)""")
    conn.commit()
    conn.close()

class GPSData:
    def __init__(self):
        self.lat = -38.3521
        self.lon = 144.2874
        self.alt = 42.0
        self.speed = 0.0
        self.fix = "3D"
        self.satellites = 8
        self.timestamp = datetime.now().isoformat()

    def update(self):
        self.lat += random.uniform(-0.0001, 0.0001)
        self.lon += random.uniform(-0.0001, 0.0001)
        self.speed = random.uniform(0, 2)
        self.satellites = random.randint(6, 12)
        self.timestamp = datetime.now().isoformat()
        conn = sqlite3.connect(DB_PATH)
        conn.execute("INSERT INTO gps_log VALUES (NULL,?,?,?,?,?)",
            (self.timestamp, self.lat, self.lon, self.alt, self.speed))
        conn.commit()
        conn.close()

class SDRData:
    def __init__(self):
        self.frequency = 433.9
        self.gain = 38
        self.hits = []
        self.aircraft = []
        self.signal_strength = -45.0

    def update(self, gps):
        self.signal_strength = random.uniform(-60, -30)
        self.frequency += random.uniform(-0.1, 0.1)
        if random.random() > 0.7:
            hit = {
                "freq": round(random.choice([433.9, 315.0, 868.0, 915.0]), 1),
                "type": random.choice(["temperature_sensor", "door_sensor", "car_key", "weather_station"]),
                "signal": round(random.uniform(-80, -40), 1),
                "timestamp": datetime.now().isoformat()
            }
            self.hits.append(hit)
            if len(self.hits) > 10:
                self.hits.pop(0)
            conn = sqlite3.connect(DB_PATH)
            conn.execute("INSERT INTO sdr_log VALUES (NULL,?,?,?,?,?,?)",
                (hit["timestamp"], hit["freq"], hit["signal"], hit["type"], gps.lat, gps.lon))
            conn.commit()
            conn.close()
        if random.random() > 0.8:
            aircraft = {
                "callsign": random.choice(["QFA123", "JST456", "VOZ789", "REX321", "TGW654"]),
                "icao": hex(random.randint(0x700000, 0x7FFFFF))[2:].upper(),
                "alt": random.randint(5000, 35000),
                "speed": random.randint(250, 500),
                "heading": random.randint(0, 359),
                "lat": gps.lat + random.uniform(-1, 1),
                "lon": gps.lon + random.uniform(-1, 1),
                "distance": round(random.uniform(5, 200), 1)
            }
            self.aircraft.append(aircraft)
            if len(self.aircraft) > 5:
                self.aircraft.pop(0)
            conn = sqlite3.connect(DB_PATH)
            conn.execute("INSERT INTO aircraft_log VALUES (NULL,?,?,?,?,?,?,?,?,?)",
                (datetime.now().isoformat(), aircraft["callsign"], aircraft["icao"],
                aircraft["alt"], aircraft["speed"], aircraft["heading"],
                aircraft["lat"], aircraft["lon"], aircraft["distance"]))
            conn.commit()
            conn.close()

class DroneData:
    def __init__(self):
        self.drones = []
        self.alerts = []
        self.remote_id_active = True
        self.droneid_active = True

    def update(self, gps):
        if random.random() > 0.92:
            methods = ["DJI_DRONEID", "REMOTE_ID_WIFI", "REMOTE_ID_BT", "RF_433MHZ", "RF_2_4GHZ"]
            models = ["DJI Mini 2", "DJI Mini 3 Pro", "DJI Mavic Air 2", "Unknown UAV", "RC Aircraft"]
            threat = random.choice(["LOW", "LOW", "MEDIUM", "HIGH"])
            drone = {
                "id": f"UAV-{random.randint(1000,9999)}",
                "model": random.choice(models),
                "lat": gps.lat + random.uniform(-0.05, 0.05),
                "lon": gps.lon + random.uniform(-0.05, 0.05),
                "alt": round(random.uniform(10, 400), 1),
                "speed": round(random.uniform(0, 15), 1),
                "operator_lat": gps.lat + random.uniform(-0.1, 0.1),
                "operator_lon": gps.lon + random.uniform(-0.1, 0.1),
                "method": random.choice(methods),
                "threat": threat,
                "timestamp": datetime.now().strftime("%H:%M:%S"),
                "distance": round(random.uniform(50, 2000), 0)
            }
            self.drones.append(drone)
            if len(self.drones) > 5:
                self.drones.pop(0)
            if threat in ["MEDIUM", "HIGH"]:
                self.alerts.append(f"[{drone['timestamp']}] {threat} THREAT -- {drone['model']} at {drone['distance']}m")
                if len(self.alerts) > 5:
                    self.alerts.pop(0)
            conn = sqlite3.connect(DB_PATH)
            conn.execute("INSERT INTO drone_log VALUES (NULL,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (datetime.now().isoformat(), drone["id"], drone["model"],
                drone["lat"], drone["lon"], drone["alt"], drone["speed"],
                drone["operator_lat"], drone["operator_lon"],
                drone["method"], drone["threat"], gps.lat, gps.lon))
            conn.commit()
            conn.close()

class WiFiData:
    def __init__(self):
        self.networks = [
            {"ssid": "Telstra_5G_Home_44A2", "bssid": "AA:BB:CC:DD:EE:FF", "signal": -61, "enc": "WPA2", "ch": 6},
            {"ssid": "OPTUS_B818_77F1", "bssid": "11:22:33:44:55:66", "signal": -74, "enc": "WPA3", "ch": 11},
            {"ssid": "AndroidAP_temp", "bssid": "DE:AD:BE:EF:CA:FE", "signal": -58, "enc": "OPEN", "ch": 1},
            {"ssid": "JanJucSurf_2.4G", "bssid": "FF:EE:DD:CC:BB:AA", "signal": -82, "enc": "WPA2", "ch": 9},
        ]
        self.handshakes = []
        self.interface = "wlan1"
        self.mode = "MONITOR"

    def update(self, gps):
        for net in self.networks:
            net["signal"] += random.randint(-2, 2)
        if random.random() > 0.95:
            net = random.choice(self.networks)
            conn = sqlite3.connect(DB_PATH)
            conn.execute("INSERT INTO wifi_log VALUES (NULL,?,?,?,?,?,?,?,?)",
                (datetime.now().isoformat(), net["ssid"], net["bssid"],
                net["signal"], net["enc"], net["ch"], gps.lat, gps.lon))
            conn.commit()
            conn.close()

class LoRaData:
    def __init__(self):
        self.nodes = [
            {"id": "NODE-01", "rssi": -87, "bat": 78, "temp": 19, "last_msg": "all clear, pos locked"},
            {"id": "NODE-02", "rssi": -94, "bat": 62, "temp": 21, "last_msg": "bat 62% temp 21c"},
        ]
        self.messages = []
        self.frequency = 915.0

    def update(self, gps):
        if random.random() > 0.85:
            node = random.choice(self.nodes)
            msg = {
                "node": node["id"],
                "rssi": node["rssi"] + random.randint(-3, 3),
                "text": random.choice([
                    "all clear", "motion detected", f"bat {node['bat']}%",
                    f"temp {node['temp']}c", "pos locked", "signal weak"
                ]),
                "timestamp": datetime.now().strftime("%H:%M:%S")
            }
            self.messages.append(msg)
            if len(self.messages) > 20:
                self.messages.pop(0)
            conn = sqlite3.connect(DB_PATH)
            conn.execute("INSERT INTO lora_log VALUES (NULL,?,?,?,?,?,?)",
                (datetime.now().isoformat(), msg["node"], msg["text"],
                msg["rssi"], gps.lat, gps.lon))
            conn.commit()
            conn.close()

class SystemData:
    def __init__(self):
        self.cpu = 0.0
        self.ram_used = 0.0
        self.ram_total = 16.0
        self.temp = 0.0
        self.battery = 78
        self.uptime = 0
        self.sdr_on = True
        self.gps_on = True
        self.lora_on = True
        self.start_time = time.time()

    def update(self):
        self.cpu = round(random.uniform(15, 45), 1)
        self.ram_used = round(random.uniform(0.8, 2.5), 1)
        self.temp = round(random.uniform(48, 58), 1)
        self.battery = max(0, self.battery - random.uniform(0, 0.01))
        self.uptime = int(time.time() - self.start_time)

class FieldKitData:
    def __init__(self):
        init_db()
        self.gps = GPSData()
        self.sdr = SDRData()
        self.wifi = WiFiData()
        self.lora = LoRaData()
        self.system = SystemData()
        self.drone = DroneData()

    def update(self):
        self.gps.update()
        self.sdr.update(self.gps)
        self.wifi.update(self.gps)
        self.lora.update(self.gps)
        self.system.update()
        self.drone.update(self.gps)

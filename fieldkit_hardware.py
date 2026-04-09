import subprocess
import threading
import socket
import json
import time
import os

HARDWARE_STATUS = {
    "rtlsdr": False,
    "gps": False,
    "lora": False,
    "wifi_monitor": False,
    "dump1090": False,
    "kismet": False,
}

def check_hardware():
    try:
        result = subprocess.run(["rtl_test", "-t"], capture_output=True, timeout=3)
        HARDWARE_STATUS["rtlsdr"] = result.returncode == 0
    except:
        HARDWARE_STATUS["rtlsdr"] = False

    try:
        sock = socket.socket()
        sock.connect(("localhost", 2947))
        sock.close()
        HARDWARE_STATUS["gps"] = True
    except:
        HARDWARE_STATUS["gps"] = False

    try:
        sock = socket.socket()
        sock.connect(("localhost", 30003))
        sock.close()
        HARDWARE_STATUS["dump1090"] = True
    except:
        HARDWARE_STATUS["dump1090"] = False

    try:
        result = subprocess.run(["meshtastic", "--info"],
            capture_output=True, timeout=3)
        HARDWARE_STATUS["lora"] = result.returncode == 0
    except:
        HARDWARE_STATUS["lora"] = False

    try:
        result = subprocess.run(
            ["curl", "-s", "http://localhost:2501/system/status.json"],
            capture_output=True, timeout=2)
        HARDWARE_STATUS["kismet"] = result.returncode == 0
    except:
        HARDWARE_STATUS["kismet"] = False

    return HARDWARE_STATUS

class GPSConnector:
    def __init__(self, sim_data):
        self.sim = sim_data
        self.real_available = False

    def get(self):
        if HARDWARE_STATUS["gps"]:
            try:
                import gps
                session = gps.gps(mode=gps.WATCH_ENABLE)
                report = session.next()
                if report["class"] == "TPV":
                    return {
                        "lat": getattr(report, "lat", self.sim.lat),
                        "lon": getattr(report, "lon", self.sim.lon),
                        "alt": getattr(report, "alt", self.sim.alt),
                        "speed": getattr(report, "speed", 0),
                        "fix": "3D" if getattr(report, "mode", 0) == 3 else "2D",
                        "satellites": 8,
                        "source": "HARDWARE"
                    }
            except:
                pass
        return {
            "lat": self.sim.lat,
            "lon": self.sim.lon,
            "alt": self.sim.alt,
            "speed": self.sim.speed,
            "fix": self.sim.fix,
            "satellites": self.sim.satellites,
            "source": "SIMULATED"
        }

class AircraftConnector:
    def __init__(self, sim_data):
        self.sim = sim_data
        self.real_aircraft = []
        self._thread = None

    def start(self):
        if HARDWARE_STATUS["dump1090"]:
            self._thread = threading.Thread(
                target=self._read_dump1090, daemon=True)
            self._thread.start()

    def _read_dump1090(self):
        while True:
            try:
                sock = socket.socket()
                sock.connect(("localhost", 30003))
                sock.settimeout(2)
                buffer = ""
                while True:
                    data = sock.recv(1024).decode("utf-8", errors="ignore")
                    buffer += data
                    while "\n" in buffer:
                        line, buffer = buffer.split("\n", 1)
                        aircraft = self._parse_sbs(line.strip())
                        if aircraft:
                            existing = [a for a in self.real_aircraft
                                if a["icao"] == aircraft["icao"]]
                            if existing:
                                existing[0].update(aircraft)
                            else:
                                self.real_aircraft.append(aircraft)
                            self.real_aircraft = self.real_aircraft[-20:]
            except:
                time.sleep(2)

    def _parse_sbs(self, line):
        try:
            parts = line.split(",")
            if len(parts) < 18 or parts[0] != "MSG":
                return None
            icao = parts[4]
            callsign = parts[10].strip() or icao
            alt = int(parts[11]) if parts[11] else None
            speed = int(float(parts[12])) if parts[12] else None
            heading = int(float(parts[13])) if parts[13] else None
            lat = float(parts[14]) if parts[14] else None
            lon = float(parts[15]) if parts[15] else None
            if not all([callsign, alt, lat, lon]):
                return None
            return {
                "callsign": callsign,
                "icao": icao,
                "alt": alt,
                "speed": speed or 0,
                "heading": heading or 0,
                "lat": lat,
                "lon": lon,
                "distance": 0,
                "source": "HARDWARE"
            }
        except:
            return None

    def get(self):
        if HARDWARE_STATUS["dump1090"] and self.real_aircraft:
            return self.real_aircraft
        return self.sim.aircraft

class WiFiConnector:
    def __init__(self, sim_data):
        self.sim = sim_data
        self.real_networks = []

    def get(self):
        if HARDWARE_STATUS["kismet"]:
            try:
                result = subprocess.run(
                    ["curl", "-s",
                     "http://localhost:2501/devices/views/all/devices.json"],
                    capture_output=True, timeout=2)
                devices = json.loads(result.stdout)
                networks = []
                for d in devices[:20]:
                    if d.get("kismet.device.base.phyname") == "IEEE802.11":
                        networks.append({
                            "ssid": d.get("kismet.device.base.name", "HIDDEN"),
                            "bssid": d.get("kismet.device.base.macaddr", ""),
                            "signal": d.get("kismet.device.base.signal", {}).get(
                                "kismet.common.signal.last_signal", -90),
                            "enc": "OPEN" if not d.get("kismet.device.base.crypt_string") else "WPA2",
                            "ch": d.get("kismet.device.base.channel", 0),
                            "source": "HARDWARE"
                        })
                return networks if networks else self.sim.networks
            except:
                pass
        return self.sim.networks

class LoRaConnector:
    def __init__(self, sim_data):
        self.sim = sim_data
        self.real_messages = []
        self._thread = None

    def start(self):
        if HARDWARE_STATUS["lora"]:
            self._thread = threading.Thread(
                target=self._read_meshtastic, daemon=True)
            self._thread.start()

    def _read_meshtastic(self):
        while True:
            try:
                result = subprocess.run(
                    ["meshtastic", "--listen", "--export-csv", "/tmp/mesh.json"],
                    capture_output=True, timeout=10)
                if os.path.exists("/tmp/mesh.json"):
                    with open("/tmp/mesh.json") as f:
                        for line in f:
                            try:
                                msg = json.loads(line)
                                self.real_messages.append({
                                    "node": msg.get("from", "UNKNOWN"),
                                    "text": msg.get("text", ""),
                                    "rssi": msg.get("rxRssi", -90),
                                    "timestamp": time.strftime("%H:%M:%S"),
                                    "source": "HARDWARE"
                                })
                            except:
                                pass
                    self.real_messages = self.real_messages[-20:]
            except:
                pass
            time.sleep(5)

    def get_messages(self):
        if HARDWARE_STATUS["lora"] and self.real_messages:
            return self.real_messages
        return self.sim.messages

class SDRConnector:
    def __init__(self, sim_data):
        self.sim = sim_data
        self.real_hits = []
        self._thread = None

    def start(self):
        if HARDWARE_STATUS["rtlsdr"]:
            self._thread = threading.Thread(
                target=self._read_rtl433, daemon=True)
            self._thread.start()

    def _read_rtl433(self):
        while True:
            try:
                proc = subprocess.Popen(
                    ["rtl_433", "-F", "json", "-f", "433920000"],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL
                )
                for line in proc.stdout:
                    try:
                        hit = json.loads(line.decode())
                        self.real_hits.append({
                            "freq": 433.9,
                            "type": hit.get("model", "unknown"),
                            "signal": hit.get("rssi", -70),
                            "timestamp": hit.get("time", ""),
                            "source": "HARDWARE",
                            "raw": hit
                        })
                        self.real_hits = self.real_hits[-20:]
                    except:
                        pass
            except:
                time.sleep(3)

    def get_hits(self):
        if HARDWARE_STATUS["rtlsdr"] and self.real_hits:
            return self.real_hits
        return self.sim.hits

def hardware_status_string():
    check_hardware()
    parts = []
    icons = {
        "rtlsdr": "SDR",
        "gps": "GPS",
        "lora": "LORA",
        "dump1090": "ADS-B",
        "kismet": "WIFI",
    }
    for key, label in icons.items():
        status = "[ON] " if HARDWARE_STATUS[key] else "[SIM]"
        parts.append(f"{label}:{status}")
    return "  ".join(parts)

if __name__ == "__main__":
    print("FIELDKIT HARDWARE CHECK")
    print("=" * 40)
    status = check_hardware()
    for k, v in status.items():
        print(f"  {k:<20} {'DETECTED' if v else 'NOT FOUND -- using simulation'}")
    print()
    print("When hardware is connected each module")
    print("switches automatically from SIM to REAL data.")
    print()
    print(hardware_status_string())

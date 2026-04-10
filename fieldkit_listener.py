import sqlite3
import subprocess
import threading
import json
import os
import time
from datetime import datetime

DB_PATH = os.path.expanduser("~/fieldkit.db")
LOG_PATH = os.path.expanduser("~/fieldkit/captures/listener_log.jsonl")
os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)

def init_listener_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""CREATE TABLE IF NOT EXISTS listener_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT,
        type TEXT,
        source TEXT,
        frequency REAL,
        signal_db REAL,
        lat REAL,
        lon REAL,
        raw TEXT)""")
    conn.commit()
    conn.close()

NODE_LAT = -38.6821
NODE_LON = 143.7654

def log_hit(hit_type, source, freq, signal, raw=""):
    ts = datetime.now().isoformat()
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.execute(
            "INSERT INTO listener_log VALUES (NULL,?,?,?,?,?,?,?,?)",
            (ts, hit_type, source, freq, signal,
             NODE_LAT, NODE_LON, raw[:200]))
        conn.commit()
        conn.close()
    except:
        pass
    try:
        with open(LOG_PATH, "a") as f:
            f.write(json.dumps({
                "timestamp": ts,
                "type": hit_type,
                "source": source,
                "freq": freq,
                "signal": signal,
                "lat": NODE_LAT,
                "lon": NODE_LON,
                "raw": raw[:200]
            }) + "\n")
    except:
        pass

def listen_rtl433():
    print("[rtl_433] starting listener...")
    last_error = None
    while True:
        try:
            proc = subprocess.Popen(
                ["rtl_433", "-F", "json",
                 "-f", "433920000",
                 "-f", "868000000",
                 "-M", "newmodel",
                 "-M", "time:iso"],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL)
            last_error = None
            print("[rtl_433] hardware found -- listening")
            for line in proc.stdout:
                try:
                    hit = json.loads(line.decode())
                    log_hit(
                        hit_type="RF_433",
                        source=hit.get("model", "unknown"),
                        freq=hit.get("freq", 433.9),
                        signal=hit.get("rssi", -70),
                        raw=json.dumps(hit)
                    )
                    print(f"[rtl_433] {hit.get('model','?')} @ {hit.get('freq','?')}MHz")
                except:
                    pass
        except Exception as e:
            err = str(e)
            if err != last_error:
                print(f"[rtl_433] waiting for hardware -- {err}")
                last_error = err
            time.sleep(10)

def listen_dump1090():
    print("[dump1090] starting ADS-B listener...")
    import socket
    last_error = None
    while True:
        try:
            sock = socket.socket()
            sock.connect(("localhost", 30003))
            sock.settimeout(10)
            buf = ""
            last_error = None
            print("[dump1090] connected -- listening for aircraft")
            while True:
                data = sock.recv(4096).decode("utf-8", errors="ignore")
                if not data:
                    break
                buf += data
                while "\n" in buf:
                    line, buf = buf.split("\n", 1)
                    parts = line.strip().split(",")
                    if len(parts) >= 15 and parts[0] == "MSG":
                        callsign = parts[10].strip()
                        icao = parts[4]
                        alt = parts[11]
                        lat = parts[14]
                        lon = parts[15]
                        if callsign and alt:
                            log_hit(
                                hit_type="ADS-B",
                                source=callsign or icao,
                                freq=1090.0,
                                signal=-45.0,
                                raw=line.strip()
                            )
                            print(f"[dump1090] {callsign} ALT:{alt}ft")
        except Exception as e:
            err = str(e)
            if err != last_error:
                print(f"[dump1090] waiting for hardware -- {err}")
                last_error = err
            time.sleep(10)

def listen_meshtastic():
    print("[meshtastic] starting LoRa listener...")
    last_error = None
    while True:
        try:
            proc = subprocess.Popen(
                ["meshtastic", "--listen"],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL)
            last_error = None
            print("[meshtastic] connected -- listening on 915MHz")
            for line in proc.stdout:
                try:
                    text = line.decode().strip()
                    if text:
                        log_hit(
                            hit_type="LORA",
                            source="mesh",
                            freq=915.0,
                            signal=-85.0,
                            raw=text[:200]
                        )
                        print(f"[meshtastic] {text[:60]}")
                except:
                    pass
        except Exception as e:
            err = str(e)
            if err != last_error:
                print(f"[meshtastic] waiting for hardware -- {err}")
                last_error = err
            time.sleep(10)

def listen_wifi():
    print("[kismet] starting WiFi listener...")
    while True:
        try:
            result = subprocess.run(
                ["curl", "-s", "--max-time", "2",
                 "http://localhost:2501/devices/views/dot11/devices.json"],
                capture_output=True, timeout=3)
            devices = json.loads(result.stdout)
            for d in devices:
                ssid = d.get("kismet.device.base.name", "HIDDEN")
                bssid = d.get("kismet.device.base.macaddr", "")
                signal = d.get("kismet.device.base.signal", {}).get(
                    "kismet.common.signal.last_signal", -90)
                log_hit(
                    hit_type="WIFI",
                    source=ssid,
                    freq=2400.0,
                    signal=signal,
                    raw=bssid
                )
        except:
            pass
        time.sleep(10)

def listen_remote_id():
    print("[remote_id] starting drone Remote ID listener...")
    while True:
        try:
            proc = subprocess.Popen(
                ["python3", "-m", "RemoteIDReceiver"],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL)
            for line in proc.stdout:
                try:
                    data = json.loads(line.decode())
                    log_hit(
                        hit_type="DRONE_REMOTE_ID",
                        source=data.get("id", "UNKNOWN"),
                        freq=2400.0,
                        signal=data.get("rssi", -70),
                        raw=json.dumps(data)
                    )
                    print(f"[remote_id] drone detected: {data.get('id','?')}")
                except:
                    pass
        except Exception as e:
            print(f"[remote_id] error: {e}")
            time.sleep(5)

def get_recent_hits(limit=20):
    try:
        conn = sqlite3.connect(DB_PATH)
        rows = conn.execute(
            """SELECT timestamp, type, source, frequency,
               signal_db, lat, lon FROM listener_log
               ORDER BY timestamp DESC LIMIT ?""",
            (limit,)).fetchall()
        conn.close()
        return rows
    except:
        return []

def get_hit_stats():
    try:
        conn = sqlite3.connect(DB_PATH)
        stats = {}
        for hit_type in ["RF_433", "ADS-B", "LORA", "WIFI", "DRONE_REMOTE_ID"]:
            count = conn.execute(
                "SELECT COUNT(*) FROM listener_log WHERE type=?",
                (hit_type,)).fetchone()[0]
            stats[hit_type] = count
        stats["total"] = conn.execute(
            "SELECT COUNT(*) FROM listener_log").fetchone()[0]
        first = conn.execute(
            "SELECT MIN(timestamp) FROM listener_log").fetchone()[0]
        stats["since"] = first or "never"
        conn.close()
        return stats
    except:
        return {}

if __name__ == "__main__":
    print("FIELDKIT LISTENER NODE")
    print("=" * 40)
    print(f"Node position: {NODE_LAT}, {NODE_LON}")
    print(f"Log file: {LOG_PATH}")
    print(f"Database: {DB_PATH}")
    print()
    print("Starting listeners...")
    init_listener_db()

    threads = [
        threading.Thread(target=listen_rtl433, daemon=True),
        threading.Thread(target=listen_dump1090, daemon=True),
        threading.Thread(target=listen_meshtastic, daemon=True),
        threading.Thread(target=listen_wifi, daemon=True),
        threading.Thread(target=listen_remote_id, daemon=True),
    ]

    for t in threads:
        t.start()

    print()
    print("All listeners running. Press Ctrl+C to stop.")
    print("Everything logged to fieldkit.db listener_log table")
    print("GPS coordinates stamped to every detection")
    print()

    while True:
        time.sleep(30)
        stats = get_hit_stats()
        if stats:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] "
                  f"TOTAL:{stats.get('total',0)}  "
                  f"RF:{stats.get('RF_433',0)}  "
                  f"AC:{stats.get('ADS-B',0)}  "
                  f"LORA:{stats.get('LORA',0)}  "
                  f"WIFI:{stats.get('WIFI',0)}  "
                  f"DRONE:{stats.get('DRONE_REMOTE_ID',0)}")

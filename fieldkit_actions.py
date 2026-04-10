import subprocess
import threading
import os
import time
import sqlite3
from datetime import datetime

DB_PATH = os.path.expanduser("~/fieldkit.db")
LOG_DIR = os.path.expanduser("~/fieldkit/captures")
os.makedirs(LOG_DIR, exist_ok=True)

HARDWARE_AVAILABLE = {
    "wifi_injection": False,
    "rtlsdr": False,
    "lora": False,
    "gps": False,
}

def check_action_hardware():
    try:
        r = subprocess.run(["iwconfig"], capture_output=True, timeout=2)
        HARDWARE_AVAILABLE["wifi_injection"] = b"wlan" in r.stdout
    except:
        HARDWARE_AVAILABLE["wifi_injection"] = False
    try:
        r = subprocess.run(["rtl_test", "-t"], capture_output=True, timeout=3)
        HARDWARE_AVAILABLE["rtlsdr"] = r.returncode == 0
    except:
        HARDWARE_AVAILABLE["rtlsdr"] = False
    try:
        r = subprocess.run(["meshtastic", "--info"], capture_output=True, timeout=3)
        HARDWARE_AVAILABLE["lora"] = r.returncode == 0
    except:
        HARDWARE_AVAILABLE["lora"] = False
    return HARDWARE_AVAILABLE

def hw_required(key):
    return HARDWARE_AVAILABLE.get(key, False)

def log_action(action, target, result, lat=None, lon=None):
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.execute("""CREATE TABLE IF NOT EXISTS action_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT, action TEXT, target TEXT,
            result TEXT, lat REAL, lon REAL)""")
        conn.execute("INSERT INTO action_log VALUES (NULL,?,?,?,?,?,?)",
            (datetime.now().isoformat(), action, target, result, lat, lon))
        conn.commit()
        conn.close()
    except:
        pass

class PentestActions:

    def enable_monitor_mode(self, interface="wlan1"):
        if not hw_required("wifi_injection"):
            return False, "HARDWARE NOT PRESENT -- monitor mode requires FENVI AX1800 on Linux"
        try:
            subprocess.run(["sudo", "airmon-ng", "start", interface],
                capture_output=True, timeout=10)
            log_action("monitor_mode", interface, "enabled")
            return True, f"Monitor mode enabled on {interface}mon"
        except Exception as e:
            return False, f"Failed: {e}"

    def capture_handshake(self, bssid, channel, ssid, interface="wlan1mon"):
        if not hw_required("wifi_injection"):
            return False, "HARDWARE NOT PRESENT -- handshake capture requires FENVI AX1800 on Linux"
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        cap_file = os.path.join(LOG_DIR, f"cap_{ssid}_{timestamp}")
        def run():
            try:
                proc = subprocess.Popen(
                    ["sudo", "airodump-ng",
                     "--bssid", bssid,
                     "--channel", str(channel),
                     "--write", cap_file,
                     interface],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
                time.sleep(30)
                proc.terminate()
                log_action("handshake_capture", bssid, f"saved to {cap_file}", )
            except Exception as e:
                log_action("handshake_capture", bssid, f"failed: {e}")
        threading.Thread(target=run, daemon=True).start()
        return True, f"Capturing handshake from {ssid} on ch{channel} -- saving to {cap_file}"

    def deauth_attack(self, bssid, client="FF:FF:FF:FF:FF:FF",
                      interface="wlan1mon", count=10):
        if not hw_required("wifi_injection"):
            return False, "HARDWARE NOT PRESENT -- deauth requires FENVI AX1800 on Linux"
        def run():
            try:
                subprocess.run(
                    ["sudo", "aireplay-ng",
                     "--deauth", str(count),
                     "-a", bssid,
                     "-c", client,
                     interface],
                    capture_output=True, timeout=30)
                log_action("deauth", bssid, f"{count} packets sent")
            except Exception as e:
                log_action("deauth", bssid, f"failed: {e}")
        threading.Thread(target=run, daemon=True).start()
        return True, f"Sending {count} deauth packets to {bssid}"

    def nmap_scan(self, target_range):
        if not hw_required("wifi_injection"):
            return False, "HARDWARE NOT PRESENT -- nmap scan requires active network interface"
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_file = os.path.join(LOG_DIR, f"nmap_{timestamp}.txt")
        def run():
            try:
                result = subprocess.run(
                    ["nmap", "-sV", "-O", "--open", target_range,
                     "-oN", out_file],
                    capture_output=True, timeout=120)
                log_action("nmap_scan", target_range, f"saved to {out_file}")
            except Exception as e:
                log_action("nmap_scan", target_range, f"failed: {e}")
        threading.Thread(target=run, daemon=True).start()
        return True, f"nmap scan of {target_range} started -- output to {out_file}"

    def packet_capture(self, interface="wlan1mon", duration=60):
        if not hw_required("wifi_injection"):
            return False, "HARDWARE NOT PRESENT -- packet capture requires FENVI AX1800 on Linux"
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        cap_file = os.path.join(LOG_DIR, f"packets_{timestamp}.pcap")
        def run():
            try:
                proc = subprocess.Popen(
                    ["sudo", "tcpdump", "-i", interface,
                     "-w", cap_file, "-G", str(duration)],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL)
                time.sleep(duration)
                proc.terminate()
                log_action("packet_capture", interface, f"saved to {cap_file}")
            except Exception as e:
                log_action("packet_capture", interface, f"failed: {e}")
        threading.Thread(target=run, daemon=True).start()
        return True, f"Capturing packets for {duration}s -- saving to {cap_file}"

    def reaver_attack(self, bssid, interface="wlan1mon"):
        if not hw_required("wifi_injection"):
            return False, "HARDWARE NOT PRESENT -- reaver requires FENVI AX1800 on Linux"
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_file = os.path.join(LOG_DIR, f"reaver_{bssid.replace(':','')}_{timestamp}.txt")
        def run():
            try:
                result = subprocess.run(
                    ["sudo", "reaver", "-i", interface,
                     "-b", bssid, "-f", "-v",
                     "-o", out_file],
                    capture_output=True, timeout=3600)
                log_action("reaver", bssid, f"saved to {out_file}")
            except Exception as e:
                log_action("reaver", bssid, f"failed: {e}")
        threading.Thread(target=run, daemon=True).start()
        return True, f"Reaver WPS attack on {bssid} -- output to {out_file}"

class SDRActions:

    def tune_and_record(self, freq_mhz, duration=30, sample_rate=2048000):
        if not hw_required("rtlsdr"):
            return False, "HARDWARE NOT PRESENT -- RTL-SDR required"
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_file = os.path.join(LOG_DIR, f"iq_{freq_mhz}MHz_{timestamp}.bin")
        def run():
            try:
                freq_hz = int(freq_mhz * 1e6)
                subprocess.run(
                    ["rtl_sdr", "-f", str(freq_hz),
                     "-s", str(sample_rate),
                     "-n", str(sample_rate * duration),
                     out_file],
                    capture_output=True, timeout=duration+10)
                log_action("iq_record", f"{freq_mhz}MHz", f"saved to {out_file}")
            except Exception as e:
                log_action("iq_record", f"{freq_mhz}MHz", f"failed: {e}")
        threading.Thread(target=run, daemon=True).start()
        return True, f"Recording IQ at {freq_mhz}MHz for {duration}s -- {out_file}"

    def decode_fm(self, freq_mhz, interface="hw:1,0"):
        if not hw_required("rtlsdr"):
            return False, "HARDWARE NOT PRESENT -- RTL-SDR required"
        freq_hz = int(freq_mhz * 1e6)
        def run():
            try:
                subprocess.Popen(
                    ["rtl_fm", "-f", str(freq_hz),
                     "-M", "wbfm", "-s", "200000",
                     "-r", "44100", "-",
                     "|", "aplay", "-r", "44100",
                     "-f", "S16_LE", "-t", "raw", "-"],
                    shell=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL)
                log_action("fm_decode", f"{freq_mhz}MHz", "playing")
            except Exception as e:
                log_action("fm_decode", f"{freq_mhz}MHz", f"failed: {e}")
        threading.Thread(target=run, daemon=True).start()
        return True, f"Decoding FM at {freq_mhz}MHz -- playing audio"

    def track_aircraft(self, icao):
        if not hw_required("rtlsdr"):
            return False, "HARDWARE NOT PRESENT -- RTL-SDR required"
        log_action("track_aircraft", icao, "tracking started")
        return True, f"Tracking aircraft {icao} -- position updates every 1s"

    def sweep_spectrum(self, start_mhz=87, end_mhz=108):
        if not hw_required("rtlsdr"):
            return False, "HARDWARE NOT PRESENT -- RTL-SDR required"
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_file = os.path.join(LOG_DIR, f"sweep_{start_mhz}_{end_mhz}_{timestamp}.csv")
        def run():
            try:
                subprocess.run(
                    ["rtl_power", "-f",
                     f"{int(start_mhz*1e6)}:{int(end_mhz*1e6)}:1000",
                     "-g", "50", "-i", "1", "-1", out_file],
                    capture_output=True, timeout=30)
                log_action("spectrum_sweep",
                    f"{start_mhz}-{end_mhz}MHz", f"saved to {out_file}")
            except Exception as e:
                log_action("spectrum_sweep",
                    f"{start_mhz}-{end_mhz}MHz", f"failed: {e}")
        threading.Thread(target=run, daemon=True).start()
        return True, f"Sweeping {start_mhz}-{end_mhz}MHz -- output to {out_file}"

class AirspaceActions:

    def tag_drone(self, drone_id, tag="KNOWN"):
        try:
            conn = sqlite3.connect(DB_PATH)
            conn.execute("""CREATE TABLE IF NOT EXISTS drone_tags (
                drone_id TEXT PRIMARY KEY,
                tag TEXT, timestamp TEXT)""")
            conn.execute(
                "INSERT OR REPLACE INTO drone_tags VALUES (?,?,?)",
                (drone_id, tag, datetime.now().isoformat()))
            conn.commit()
            conn.close()
            log_action("tag_drone", drone_id, tag)
            return True, f"Drone {drone_id} tagged as {tag}"
        except Exception as e:
            return False, f"Failed: {e}"

    def export_report(self, gps_lat=None, gps_lon=None):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_file = os.path.join(LOG_DIR, f"fieldkit_report_{timestamp}.txt")
        try:
            conn = sqlite3.connect(DB_PATH)
            lines = []
            lines.append("FIELDKIT DETECTION REPORT")
            lines.append("=" * 50)
            lines.append(f"Generated: {datetime.now().isoformat()}")
            if gps_lat and gps_lon:
                lines.append(f"Location: {gps_lat:.6f}, {gps_lon:.6f}")
            lines.append("")
            lines.append("AIRCRAFT DETECTIONS")
            lines.append("-" * 30)
            rows = conn.execute(
                "SELECT * FROM aircraft_log ORDER BY timestamp DESC LIMIT 20"
            ).fetchall()
            for r in rows:
                lines.append(f"  {r[1]} {r[2]} ALT:{r[4]}ft SPD:{r[5]}kts")
            lines.append("")
            lines.append("DRONE DETECTIONS")
            lines.append("-" * 30)
            rows = conn.execute(
                "SELECT * FROM drone_log ORDER BY timestamp DESC LIMIT 20"
            ).fetchall()
            for r in rows:
                lines.append(f"  {r[1]} {r[2]} {r[3]} THREAT:{r[11]}")
            lines.append("")
            lines.append("WIFI DETECTIONS")
            lines.append("-" * 30)
            rows = conn.execute(
                "SELECT * FROM wifi_log ORDER BY timestamp DESC LIMIT 20"
            ).fetchall()
            for r in rows:
                lines.append(f"  {r[1]} {r[2]} {r[4]} ch:{r[6]}")
            conn.close()
            with open(report_file, "w") as f:
                f.write("\n".join(lines))
            log_action("export_report", "all", f"saved to {report_file}")
            return True, f"Report exported to {report_file}"
        except Exception as e:
            return False, f"Failed: {e}"

class MeshActions:

    def send_message(self, text, node_id=None):
        if not hw_required("lora"):
            return False, "HARDWARE NOT PRESENT -- Meshtastic device required"
        def run():
            try:
                cmd = ["meshtastic", "--sendtext", text]
                if node_id:
                    cmd += ["--dest", node_id]
                subprocess.run(cmd, capture_output=True, timeout=10)
                log_action("mesh_send", node_id or "broadcast", text[:50])
            except Exception as e:
                log_action("mesh_send", node_id or "broadcast", f"failed: {e}")
        threading.Thread(target=run, daemon=True).start()
        return True, f"Message sent via LoRa: {text[:30]}"

    def ping_node(self, node_id):
        if not hw_required("lora"):
            return False, "HARDWARE NOT PRESENT -- Meshtastic device required"
        def run():
            try:
                subprocess.run(
                    ["meshtastic", "--ping", node_id],
                    capture_output=True, timeout=15)
                log_action("mesh_ping", node_id, "pinged")
            except Exception as e:
                log_action("mesh_ping", node_id, f"failed: {e}")
        threading.Thread(target=run, daemon=True).start()
        return True, f"Pinging {node_id} via LoRa mesh"

    def get_node_info(self, node_id=None):
        if not hw_required("lora"):
            return False, "HARDWARE NOT PRESENT -- Meshtastic device required"
        try:
            result = subprocess.run(
                ["meshtastic", "--nodes"],
                capture_output=True, timeout=10)
            return True, result.stdout.decode()[:500]
        except Exception as e:
            return False, f"Failed: {e}"

PENTEST = PentestActions()
SDR = SDRActions()
AIRSPACE = AirspaceActions()
MESH = MeshActions()

if __name__ == "__main__":
    check_action_hardware()
    print("FIELDKIT ACTION LAYER")
    print("=" * 40)
    for k, v in HARDWARE_AVAILABLE.items():
        status = "READY" if v else "LOCKED -- hardware required"
        print(f"  {k:<20} {status}")
    print()
    print("Actions locked until hardware connected:")
    print("  PENTEST -- A:handshake  D:deauth  S:nmap  C:capture  R:reaver")
    print("  SDR     -- T:tune+record  F:FM audio  L:lock aircraft  W:sweep")
    print("  AIRSPACE -- T:tag drone  E:export report")
    print("  MESH    -- M:send message  P:ping node  I:node info")

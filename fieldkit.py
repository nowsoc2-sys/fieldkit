from textual.app import App, ComposeResult
from textual.widgets import Static, Label
from textual.containers import Container, Horizontal
from textual import events
from fieldkit_data import FieldKitData
from datetime import datetime
import math
import json
import os
import subprocess
import threading

CSS = """
Screen {
    background: #0a0f0a;
    layout: vertical;
}
#topbar {
    height: 3;
    background: #0d130d;
    border-bottom: solid #00ff41;
    layout: horizontal;
}
#mode_label {
    color: #00ff41;
    text-style: bold;
    padding: 1 2;
    width: 40%;
}
#status_bar {
    color: #3a6a3a;
    padding: 1 2;
    width: 60%;
    text-align: right;
}
#main_panel {
    background: #0a0f0a;
    border: solid #1a2e1a;
    padding: 1 2;
    margin: 0 1;
    height: 1fr;
    width: 100%;
}
#panel_content {
    color: #00ff41;
    height: 100%;
    width: 100%;
}
#nav {
    height: 3;
    background: #080e08;
    border-top: solid #00ff41;
    layout: horizontal;
}
.nav_btn {
    color: #3a6a3a;
    padding: 1 0;
    width: 1fr;
    text-align: center;
}
.active {
    color: #00ff41;
    text-style: bold;
}
"""

MODES = {1: "RECON", 2: "SDR", 3: "MESH", 4: "PENTEST", 5: "AIRSPACE", 6: "SYSTEM"}
W = 74
DATA_FILE = os.path.expanduser("~/fieldkit_live.json")

def bar(val, lo, hi, width=20, unit=""):
    pct = min(1.0, max(0.0, (val - lo) / (hi - lo)))
    f = int(pct * width)
    return f"[{'█'*f}{'░'*(width-f)}] {val:.1f}{unit}"

def threat_icon(level):
    return {"LOW": "◆", "MEDIUM": "▲", "HIGH": "!!"}.get(level, "?")

def waterfall(hits, rows=5):
    freqs = [315.0, 350.0, 433.9, 500.0, 868.0, 915.0, 1090.0]
    lines = []
    header = "  "
    for f in freqs:
        header += f"{f:>7.1f} "
    lines.append(header)
    lines.append("  " + "─" * (len(freqs) * 9))
    for row in range(rows):
        line = "  "
        for f in freqs:
            matching = [h for h in hits if abs(h.get("freq", 0) - f) < 10]
            if matching:
                sig = max(h["signal"] for h in matching)
                intensity = min(1.0, max(0.0, (sig + 90) / 60))
                chars = ["░", "▒", "▓", "█"]
                char = chars[min(3, int(intensity * 4))]
                if f == 1090.0:
                    char = "▲"
            else:
                char = "░" if row == 0 else " "
            line += f"   {char}{char}{char}    "
        lines.append(line)
    lines.append("  " + "─" * (len(freqs) * 9))
    return "\n".join(lines)

def export_live_json(d):
    try:
        payload = {
            "timestamp": datetime.now().isoformat(),
            "gps": {
                "lat": d.gps.lat,
                "lon": d.gps.lon,
                "alt": d.gps.alt,
                "speed": d.gps.speed,
                "fix": d.gps.fix,
                "satellites": d.gps.satellites
            },
            "aircraft": d.sdr.aircraft,
            "drones": d.drone.drones,
            "wifi": d.wifi.networks,
            "rf_hits": d.sdr.hits,
            "lora_nodes": d.lora.nodes,
            "lora_messages": d.lora.messages,
            "system": {
                "cpu": d.system.cpu,
                "ram_used": d.system.ram_used,
                "temp": d.system.temp,
                "battery": d.system.battery,
                "uptime": d.system.uptime
            }
        }
        with open(DATA_FILE, "w") as f:
            json.dump(payload, f)
    except:
        pass

class FieldKit(App):
    CSS = CSS
    current_mode = 1
    map_open = False

    def __init__(self):
        super().__init__()
        self.data = FieldKitData()

    def compose(self) -> ComposeResult:
        yield Horizontal(
            Label(" FIELDKIT OS v1.0 -- RECON ", id="mode_label"),
            Label("", id="status_bar"),
            id="topbar"
        )
        yield Container(
            Static("", id="panel_content"),
            id="main_panel"
        )
        yield Horizontal(
            Label("[1]RECON", classes="nav_btn active", id="nav1"),
            Label("[2]SDR", classes="nav_btn", id="nav2"),
            Label("[3]MESH", classes="nav_btn", id="nav3"),
            Label("[4]PENTEST", classes="nav_btn", id="nav4"),
            Label("[5]AIRSPACE", classes="nav_btn", id="nav5"),
            Label("[6]SYSTEM", classes="nav_btn", id="nav6"),
            id="nav"
        )

    def on_mount(self):
        self.set_interval(1.0, self.tick)

    def tick(self):
        self.data.update()
        export_live_json(self.data)
        self.refresh_ui()

    def open_map(self):
        def run():
            subprocess.Popen(
                ["python3", os.path.expanduser("~/fieldkit/fieldkit_map.py")],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
        threading.Thread(target=run, daemon=True).start()
        self.map_open = True

    def refresh_ui(self):
        d = self.data
        now = datetime.now().strftime("%H:%M:%S")
        bat = f"BAT:{d.system.battery:.0f}%"
        gps_s = "GPS:LOCK" if d.gps.fix == "3D" else "GPS:ACQ"
        drone_alert = " !!DRONE!!" if any(dr["threat"] in ["MEDIUM","HIGH"] for dr in d.drone.drones) else ""
        open_alert = " !!OPEN NET!!" if any(n["enc"]=="OPEN" for n in d.wifi.networks) else ""
        map_status = " [M:MAP ON]" if self.map_open else " [M:MAP]"
        self.query_one("#status_bar", Label).update(
            f"{gps_s}  SDR:ON  {bat}  {now}{drone_alert}{open_alert}{map_status} ")
        self.query_one("#panel_content", Static).update(self.get_panel())

    def get_panel(self):
        d = self.data
        m = self.current_mode

        if m == 1:
            open_nets = [n for n in d.wifi.networks if n["enc"] == "OPEN"]
            high_drones = [dr for dr in d.drone.drones if dr["threat"] == "HIGH"]
            alerts = ""
            if open_nets:
                alerts += f"\n  !! {len(open_nets)} OPEN NETWORK(S) DETECTED !!"
            if high_drones:
                alerts += f"\n  !! HIGH THREAT DRONE -- {high_drones[-1]['model']} !!"
            return (
                f"\n"
                f"  {'═'*W}\n"
                f"  GPS: {d.gps.lat:.6f}  {d.gps.lon:.6f}  {d.gps.alt:.0f}m  SAT:{d.gps.satellites}  {d.gps.fix}\n"
                f"  {'─'*W}\n"
                f"  WIFI:{len(d.wifi.networks)} ({sum(1 for n in d.wifi.networks if n['enc']=='OPEN')} open)  "
                f"SDR:{len(d.sdr.hits)} hits  "
                f"AIRCRAFT:{len(d.sdr.aircraft)}  "
                f"DRONES:{len(d.drone.drones)}  "
                f"LORA:{len(d.lora.nodes)} nodes\n"
                f"  {'═'*W}\n"
                f"  LIVE MAP  --  press M to open satellite map in browser\n"
                f"  DATA  --  {DATA_FILE}\n"
                f"  {'═'*W}\n"
                f"  STATUS   ALL SYSTEMS NOMINAL{alerts}"
            )

        elif m == 2:
            wf = waterfall(d.sdr.hits)
            ac = ""
            for a in d.sdr.aircraft[-4:]:
                ac += f"  ✈ {a['callsign']:<10} {a['alt']:>6}ft  {a['speed']:>3}kts  {a['heading']:>3}°  {a['distance']:>7.1f}km\n"
            if not ac:
                ac = "  no aircraft detected\n"
            hits = ""
            for h in d.sdr.hits[-4:]:
                hits += f"  {h['freq']:>7.1f}MHz  {h['type']:<22} {h['signal']:>6.1f}dBm\n"
            if not hits:
                hits = "  no hits\n"
            return (
                f"\n"
                f"  {'═'*W}\n"
                f"  SDR  FREQ:{d.sdr.frequency:.2f}MHz  GAIN:{d.sdr.gain}dB  "
                f"SIG:{bar(d.sdr.signal_strength,-90,-20,15,'dB')}\n"
                f"  {'═'*W}\n"
                f"  WATERFALL\n"
                f"  {'─'*W}\n"
                f"{wf}\n"
                f"  {'═'*W}\n"
                f"  AIRCRAFT ADS-B ({len(d.sdr.aircraft)} detected)\n"
                f"  {'─'*W}\n"
                f"{ac}"
                f"  {'═'*W}\n"
                f"  RF HITS rtl_433 ({len(d.sdr.hits)} decoded)\n"
                f"  {'─'*W}\n"
                f"{hits}"
            )

        elif m == 3:
            nodes = ""
            for n in d.lora.nodes:
                nodes += f"  {n['id']:<12} {bar(n['rssi'],-120,-60,15,'dBm')}  BAT:{n['bat']}%  {n['temp']}c\n"
            msgs = ""
            for msg in d.lora.messages[-8:]:
                msgs += f"  [{msg['timestamp']}] {msg['node']:<10} {msg['text']}\n"
            if not msgs:
                msgs = "  no messages\n"
            return (
                f"\n"
                f"  {'═'*W}\n"
                f"  LORA MESH  {d.lora.frequency}MHz  {len(d.lora.nodes)} nodes  {len(d.lora.messages)} msgs\n"
                f"  {'═'*W}\n"
                f"  NODE STATUS\n"
                f"  {'─'*W}\n"
                f"{nodes}"
                f"  {'═'*W}\n"
                f"  MESSAGE LOG\n"
                f"  {'─'*W}\n"
                f"{msgs}"
            )

        elif m == 4:
            nets = ""
            for n in d.wifi.networks:
                flag = " !! OPEN !!" if n["enc"] == "OPEN" else ""
                nets += f"  {n['ssid']:<26} {n['enc']:<5} ch{n['ch']:<3} {bar(n['signal'],-100,-30,15,'dBm')}{flag}\n"
            net_chart = "  SIGNAL LEVELS\n  "
            for n in d.wifi.networks:
                pct = min(1.0, max(0.0, (n['signal'] + 100) / 70))
                h = int(pct * 8)
                net_chart += f" {'█'*h}{'░'*(8-h)} "
            net_chart += "\n  "
            for n in d.wifi.networks:
                net_chart += f" {n['ssid'][:7]:<9}"
            hs = "  no handshakes captured\n" if not d.wifi.handshakes else ""
            return (
                f"\n"
                f"  {'═'*W}\n"
                f"  WIFI PENTEST  {d.wifi.interface} [{d.wifi.mode}]\n"
                f"  GPS  {d.gps.lat:.6f}  {d.gps.lon:.6f}\n"
                f"  {'═'*W}\n"
                f"{net_chart}\n"
                f"  {'─'*W}\n"
                f"{nets}"
                f"  {'═'*W}\n"
                f"  HANDSHAKES ({len(d.wifi.handshakes)} captured)\n"
                f"  {'─'*W}\n"
                f"{hs}"
                f"  ALL EVENTS LOGGED TO fieldkit.db WITH GPS TAGS"
            )

        elif m == 5:
            drones = ""
            for dr in d.drone.drones[-4:]:
                icon = threat_icon(dr["threat"])
                drones += f"  {icon} {dr['id']:<10} {dr['model']:<18} {dr['alt']:>4.0f}m  {dr['distance']:>5.0f}m\n"
                drones += f"    METHOD:{dr['method']:<20} THREAT:{dr['threat']}\n"
            if not drones:
                drones = "  no drones detected\n"
            aircraft = ""
            for a in d.sdr.aircraft[-4:]:
                aircraft += f"  ✈ {a['callsign']:<10} {a['alt']:>6}ft  {a['speed']:>3}kts  {a['distance']:>6.1f}km\n"
            if not aircraft:
                aircraft = "  no aircraft\n"
            alerts = ""
            for al in d.drone.alerts[-3:]:
                alerts += f"  {al}\n"
            if not alerts:
                alerts = "  no alerts\n"
            return (
                f"\n"
                f"  {'═'*W}\n"
                f"  AIRSPACE  DRONE-ID:ON  REMOTE-ID:ON  ADS-B:ON\n"
                f"  press M for live satellite map\n"
                f"  {'═'*W}\n"
                f"  DRONES ({len(d.drone.drones)} detected)\n"
                f"  {'─'*W}\n"
                f"{drones}"
                f"  {'═'*W}\n"
                f"  AIRCRAFT ({len(d.sdr.aircraft)} detected)\n"
                f"  {'─'*W}\n"
                f"{aircraft}"
                f"  {'═'*W}\n"
                f"  THREAT ALERTS\n"
                f"  {'─'*W}\n"
                f"{alerts}"
            )

        elif m == 6:
            up = f"{d.system.uptime//3600:02d}:{(d.system.uptime%3600)//60:02d}:{d.system.uptime%60:02d}"
            cpu_h = int((d.system.cpu / 100) * 10)
            ram_h = int((d.system.ram_used / d.system.ram_total) * 10)
            temp_h = int(((d.system.temp - 20) / 60) * 10)
            bat_h = int((d.system.battery / 100) * 10)
            chart = "  CPU  RAM  TMP  BAT\n"
            for row in range(10, -1, -1):
                line = "  "
                for h in [cpu_h, ram_h, temp_h, bat_h]:
                    if row == 0:
                        line += "───  "
                    elif row <= h:
                        line += "███  "
                    else:
                        line += "░░░  "
                chart += line + "\n"
            chart += f"  {d.system.cpu:.0f}%   {(d.system.ram_used/d.system.ram_total*100):.0f}%   {d.system.temp:.0f}c   {d.system.battery:.0f}%\n"
            sdr = "[ON]" if d.system.sdr_on else "[OFF]"
            gps = "[ON]" if d.system.gps_on else "[OFF]"
            lora = "[ON]" if d.system.lora_on else "[OFF]"
            return (
                f"\n"
                f"  {'═'*W}\n"
                f"  SYSTEM  UPTIME:{up}\n"
                f"  {'─'*W}\n"
                f"{chart}"
                f"  {'═'*W}\n"
                f"  MODULES  SDR{sdr}  GPS{gps}  LORA{lora}\n"
                f"  {'═'*W}\n"
                f"  STACK\n"
                f"  {'─'*W}\n"
                f"  ADS-B:dump1090  RF:rtl_433  DRONE:DroneSecurity\n"
                f"  WIFI:Kismet+aircrack  MESH:Meshtastic  GPS:gpsd\n"
                f"  {'═'*W}\n"
                f"  LIVE DATA  --  {DATA_FILE}\n"
                f"  FIELDKIT OS v1.0  //  fieldkit.db"
            )

    def on_key(self, event: events.Key) -> None:
        key_map = {"1":1,"2":2,"3":3,"4":4,"5":5,"6":6}
        if event.key in key_map:
            old = self.current_mode
            self.current_mode = key_map[event.key]
            self.query_one(f"#nav{old}", Label).remove_class("active")
            self.query_one(f"#nav{self.current_mode}", Label).add_class("active")
            self.query_one("#mode_label", Label).update(
                f" FIELDKIT OS v1.0 -- {MODES[self.current_mode]} ")
            self.refresh_ui()
        elif event.key == "m":
            self.open_map()

if __name__ == "__main__":
    app = FieldKit()
    app.run()

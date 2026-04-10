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
    padding: 0 1;
    margin: 0 1;
    height: 1fr;
    width: 1fr;
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
.alert_high {
    color: #ff0000;
    text-style: bold;
}
.alert_med {
    color: #ffaa00;
    text-style: bold;
}
.alert_open {
    color: #ff4444;
    text-style: bold;
}
"""

MODES = {1:"RECON",2:"SDR",3:"MESH",4:"PENTEST",5:"AIRSPACE",6:"SYSTEM"}
W = 76
DATA_FILE = os.path.expanduser("~/fieldkit_live.json")

def hbar(val, lo, hi, width=30, unit="", label=""):
    pct = min(1.0, max(0.0, (val-lo)/(hi-lo)))
    f = int(pct*width)
    empty = width-f
    if pct > 0.8:
        fill = "█"*f
    elif pct > 0.5:
        fill = "▓"*f
    elif pct > 0.3:
        fill = "▒"*f
    else:
        fill = "░"*f
    bar = f"[{fill}{'░'*empty}]"
    return f"{label:<6} {bar} {val:.1f}{unit}"

def sparkline(values, width=40):
    if not values:
        return "░" * width
    lo, hi = min(values), max(values)
    if hi == lo:
        return "▄" * min(len(values), width)
    chars = " ▁▂▃▄▅▆▇█"
    result = ""
    for v in values[-width:]:
        idx = int((v-lo)/(hi-lo)*8)
        result += chars[idx]
    return result.ljust(width, "░")

def vbar_chart(values, labels, height=8, width=6):
    if not values or max(values) == 0:
        return "  no data\n"
    mx = max(values)
    bars = []
    for v in values:
        h = int((v/mx)*height)
        col = []
        for row in range(height, 0, -1):
            if row <= h:
                if h > height*0.8:
                    col.append("█")
                elif h > height*0.5:
                    col.append("▓")
                else:
                    col.append("▒")
            else:
                col.append(" ")
        bars.append(col)
    lines = []
    for row in range(height):
        line = "  "
        for col in bars:
            line += f" {col[row]*width} "
        lines.append(line)
    lines.append("  " + "─"*(len(values)*(width+2)+2))
    label_line = "  "
    for l in labels:
        label_line += f" {l[:width]:<{width}} "
    lines.append(label_line)
    return "\n".join(lines)

def threat_ring(drones):
    low = sum(1 for d in drones if d["threat"]=="LOW")
    med = sum(1 for d in drones if d["threat"]=="MEDIUM")
    high = sum(1 for d in drones if d["threat"]=="HIGH")
    total = max(1, len(drones))
    ring = f"  [LOW:{'◆'*low if low else '-'}] [MED:{'▲'*med if med else '-'}] [HIGH:{'!!'*high if high else '-'}]"
    pct_high = (high/total)*100
    threat_bar = hbar(pct_high, 0, 100, 20, "%", "THREAT")
    return ring + "\n  " + threat_bar

def wifi_chart(networks, selected=0, max_visible=4):
    if not networks:
        return "  no networks\n"
    lines = []
    total = len(networks)
    start = max(0, selected - max_visible + 1)
    end = min(total, start + max_visible)
    if end - start < max_visible:
        start = max(0, end - max_visible)
    lines.append("  SIGNAL STRENGTH  (" + str(total) + " networks  showing " + str(start+1) + "-" + str(end) + "  UP/DOWN to scroll)")
    lines.append("")
    for i in range(start, end):
        n = networks[i]
        sig = n["signal"]
        pct = min(1.0, max(0.0, (sig+100)/70))
        w = 32
        f = int(pct*w)
        fill = chr(9608)*f if n["enc"]=="OPEN" else chr(9619)*f
        bar = "[" + fill + chr(9617)*(w-f) + "]"
        flag = " !! OPEN !!" if n["enc"]=="OPEN" else ""
        cursor = ">" if i == selected else " "
        lines.append("  " + cursor + " " + n["ssid"][:20].ljust(20) + " " + bar + " " + str(sig) + "dBm" + flag)
        lines.append("      " + n["enc"].ljust(5) + " ch" + str(n["ch"]).ljust(3) + " " + n["bssid"])
        lines.append("")
    if total > max_visible:
        above = "scroll up" if start > 0 else ""
        below = "more networks below" if end < total else ""
        lines.append("  " + above.ljust(20) + "  " + below)
    return "\n".join(lines)

def system_chart(d):
    import sqlite3
    import os
    import subprocess

    cpu = d.system.cpu
    ram_pct = (d.system.ram_used/d.system.ram_total)*100
    temp = d.system.temp
    bat = d.system.battery
    up = str(d.system.uptime//3600).zfill(2) + ":" + str((d.system.uptime%3600)//60).zfill(2) + ":" + str(d.system.uptime%60).zfill(2)

    total_aircraft = 0
    total_drones = 0
    total_wifi = 0
    total_rf = 0
    total_gps = 0
    closest_drone = "N/A"
    strongest_signal = "N/A"
    top_aircraft = "N/A"
    try:
        db = os.path.expanduser("~/fieldkit.db")
        conn = sqlite3.connect(db)
        total_aircraft = conn.execute("SELECT COUNT(*) FROM aircraft_log").fetchone()[0]
        total_drones = conn.execute("SELECT COUNT(*) FROM drone_log").fetchone()[0]
        total_wifi = conn.execute("SELECT COUNT(*) FROM wifi_log").fetchone()[0]
        total_rf = conn.execute("SELECT COUNT(*) FROM sdr_log").fetchone()[0]
        total_gps = conn.execute("SELECT COUNT(*) FROM gps_log").fetchone()[0]
        r = conn.execute("SELECT drone_id, MIN(distance) FROM drone_log WHERE distance > 0").fetchone()
        if r and r[1]:
            closest_drone = str(r[0]) + " @ " + str(round(r[1],0)) + "m"
        r = conn.execute("SELECT callsign, COUNT(*) as c FROM aircraft_log GROUP BY callsign ORDER BY c DESC LIMIT 1").fetchone()
        if r:
            top_aircraft = str(r[0]) + " (" + str(r[1]) + " hits)"
        r = conn.execute("SELECT MAX(signal_db) FROM sdr_log").fetchone()
        if r and r[0]:
            strongest_signal = str(round(r[0],1)) + " dBm"
        conn.close()
    except:
        pass

    gps_score = 25 if d.gps.fix == "3D" else 10
    bat_score = int((bat/100)*25)
    sdr_score = 25 if d.system.sdr_on else 0
    modules_score = 0
    if d.system.gps_on: modules_score += 8
    if d.system.lora_on: modules_score += 8
    if d.system.sdr_on: modules_score += 9
    readiness = gps_score + bat_score + sdr_score + modules_score
    readiness = min(100, readiness)

    if readiness >= 80:
        ready_label = "FIELD READY"
        ready_fill = chr(9608)
    elif readiness >= 50:
        ready_label = "PARTIAL"
        ready_fill = chr(9619)
    else:
        ready_label = "NOT READY"
        ready_fill = chr(9617)

    r_width = 40
    r_filled = int((readiness/100)*r_width)
    ready_bar = "[" + ready_fill*r_filled + chr(9617)*(r_width-r_filled) + "]"

    processes = [
        ("dump1090", "dump1090"),
        ("rtl_433", "rtl_433"),
        ("kismet", "kismet"),
        ("gpsd", "gpsd"),
        ("meshtastic", "meshtastic"),
    ]
    proc_status = []
    for name, proc in processes:
        try:
            r = subprocess.run(["pgrep", "-x", proc],
                capture_output=True, timeout=1)
            running = r.returncode == 0
        except:
            running = False
        dot = "[ON] " if running else "[OFF]"
        proc_status.append((name, dot))

    lines = []
    lines.append("  " + "="*76)
    lines.append("  SYSTEM TELEMETRY  //  UPTIME: " + up)
    lines.append("  " + "-"*76)
    lines.append("  " + hbar(cpu, 0, 100, 45, "%", "CPU   "))
    lines.append("  " + hbar(ram_pct, 0, 100, 45, "%", "RAM   ") + "  " + str(round(d.system.ram_used,1)) + "/" + str(int(d.system.ram_total)) + "GB")
    lines.append("  " + hbar(temp, 20, 90, 45, "c", "TEMP  "))
    lines.append("  " + hbar(bat, 0, 100, 45, "%", "BAT   "))
    lines.append("  " + "="*76)
    lines.append("  FIELD READINESS  " + str(readiness) + "/100  --  " + ready_label)
    lines.append("  " + ready_bar + "  " + ready_label)
    lines.append("  GPS:" + str(gps_score) + "/25  BAT:" + str(bat_score) + "/25  SDR:" + str(sdr_score) + "/25  MODULES:" + str(modules_score) + "/25")
    lines.append("  " + "="*76)
    lines.append("  TREND CHART")
    lines.append("  " + "-"*76)
    height = 8
    metrics = [
        ("CPU%", cpu, 0, 100),
        ("RAM%", ram_pct, 0, 100),
        ("TEMP", temp, 20, 90),
        ("BAT%", bat, 0, 100),
    ]
    col_w = 12
    for row in range(height, -1, -1):
        y_val = int((row/height)*100)
        line = "  " + str(y_val).rjust(3) + " |"
        for label, val, lo, hi in metrics:
            pct = min(1.0, max(0.0, (val-lo)/(hi-lo)))
            h = int(pct*height)
            if row == 0:
                line += "-"*col_w + "+"
            elif row <= h:
                if pct > 0.8:
                    line += chr(9608)*col_w + "|"
                elif pct > 0.5:
                    line += chr(9619)*col_w + "|"
                elif pct > 0.3:
                    line += chr(9618)*col_w + "|"
                else:
                    line += chr(9617)*col_w + "|"
            else:
                line += " "*col_w + "|"
        lines.append(line)
    val_line = "       "
    for label, val, lo, hi in metrics:
        val_line += (label + ":" + str(round(val,1))).ljust(col_w+1)
    lines.append(val_line)
    lines.append("  " + "="*76)
    lines.append("  ALL TIME DETECTION STATS  (from fieldkit.db)")
    lines.append("  " + "-"*76)
    stats_vals = [total_aircraft, total_drones, total_wifi, total_rf, total_gps]
    stats_labs = ["AC", "DRONE", "WIFI", "RF", "GPS"]
    lines.append(vbar_chart(stats_vals, stats_labs, height=5, width=6))
    lines.append("  AIRCRAFT:" + str(total_aircraft) + "  DRONES:" + str(total_drones) + "  WIFI:" + str(total_wifi) + "  RF:" + str(total_rf) + "  GPS FIXES:" + str(total_gps))
    lines.append("  CLOSEST DRONE: " + closest_drone + "  TOP AIRCRAFT: " + top_aircraft)
    lines.append("  STRONGEST SIGNAL: " + strongest_signal)
    lines.append("  " + "="*76)
    lines.append("  PROCESS STATUS")
    lines.append("  " + "-"*76)
    proc_line = "  "
    for name, dot in proc_status:
        proc_line += dot + " " + name.ljust(12) + "  "
    lines.append(proc_line)
    lines.append("  " + "="*76)
    sdr = "[LIVE]" if d.system.sdr_on else "[SIM] "
    gps = "[LIVE]" if d.system.gps_on else "[SIM] "
    lora = "[LIVE]" if d.system.lora_on else "[SIM] "
    lines.append("  SDR:" + sdr + "  GPS:" + gps + "  LORA:" + lora + "  //  FIELDKIT OS v1.0  //  NWS-C")
    return "\n".join(lines)

def airspace_chart(d, selected=0, action_result=""):
    drones = d.drone.drones
    aircraft = d.sdr.aircraft
    lines = []
    lines.append(f"  {'═'*W}")
    lines.append(f"  AIRSPACE  //  DRONE-ID:ON  REMOTE-ID:ON  ADS-B:ON")
    lines.append(f"  KEYS: UP/DOWN select  T:tag drone  E:export report")
    lines.append(f"  {'─'*W}")
    lines.append(threat_ring(drones))
    lines.append(f"  {'═'*W}")
    if drones:
        lines.append(f"  DRONES ({len(drones)} detected)")
        lines.append(f"  {'─'*W}")
        dist_vals = []
        dist_labs = []
        for i, dr in enumerate(drones[-5:]):
            icon = {"LOW":"◆","MEDIUM":"▲","HIGH":"!!"}.get(dr["threat"],"?")
            cursor = ">" if i == selected else " "
            dist_bar = hbar(min(dr["distance"],2000), 0, 2000, 20, "m", "DIST ")
            lines.append(f"  {cursor}{icon} {dr['id']:<10} {dr['model']:<16} ALT:{dr['alt']:>4.0f}m")
            lines.append(f"    {dist_bar}  METHOD:{dr['method']}  THREAT:{dr['threat']}")
            dist_vals.append(dr["distance"])
            dist_labs.append(dr["id"][-4:])
        lines.append(f"  {'─'*W}")
        lines.append(f"  DRONE DISTANCE CHART")
        lines.append(vbar_chart(dist_vals, dist_labs, height=4, width=5))
    lines.append(f"  {'═'*W}")
    if aircraft:
        lines.append(f"  AIRCRAFT ({len(aircraft)} via ADS-B)")
        lines.append(f"  {'─'*W}")
        alt_vals = []
        alt_labs = []
        for a in aircraft[-4:]:
            alt_bar = hbar(a["alt"], 0, 40000, 25, "ft", "ALT  ")
            lines.append(f"  ✈ {a['callsign']:<10} {alt_bar}  {a['speed']}kts  {a['distance']}km")
            alt_vals.append(a["alt"])
            alt_labs.append(a["callsign"][:5])
        lines.append(f"  {'─'*W}")
        lines.append(f"  ALTITUDE CHART")
        lines.append(vbar_chart(alt_vals, alt_labs, height=4, width=5))
    lines.append(f"  {'═'*W}")
    lines.append(f"  ALERTS")
    lines.append(f"  {'─'*W}")
    for al in (d.drone.alerts[-3:] or ["  no alerts"]):
        lines.append(f"  {al}")
    if action_result:
        lines.append(f"  {'─'*W}")
        lines.append(f"  ACTION: {action_result}")
    return "\n".join(lines)

def export_live_json(d):
    try:
        payload = {
            "timestamp": datetime.now().isoformat(),
            "gps": {"lat":d.gps.lat,"lon":d.gps.lon,"alt":d.gps.alt,
                    "speed":d.gps.speed,"fix":d.gps.fix,"satellites":d.gps.satellites},
            "aircraft": d.sdr.aircraft,
            "drones": d.drone.drones,
            "wifi": d.wifi.networks,
            "rf_hits": d.sdr.hits,
            "lora_nodes": d.lora.nodes,
            "lora_messages": d.lora.messages,
            "system": {"cpu":d.system.cpu,"ram_used":d.system.ram_used,
                      "temp":d.system.temp,"battery":d.system.battery,
                      "uptime":d.system.uptime}
        }
        with open(DATA_FILE, "w") as f:
            json.dump(payload, f)
    except:
        pass

class FieldKit(App):
    CSS = CSS
    current_mode = 1
    map_open = False
    action_result = ""
    selected_network = 0
    selected_drone = 0

    def __init__(self):
        super().__init__()
        self.data = FieldKitData()
        try:
            from fieldkit_actions import (
                PENTEST, SDR, AIRSPACE, MESH, check_action_hardware)
            self.pentest = PENTEST
            self.sdr_actions = SDR
            self.airspace_actions = AIRSPACE
            self.mesh = MESH
            check_action_hardware()
        except Exception as e:
            self.pentest = None
            self.sdr_actions = None
            self.airspace_actions = None
            self.mesh = None

    def compose(self) -> ComposeResult:
        yield Horizontal(
            Label(" FIELDKIT OS v1.0 -- RECON ", id="mode_label"),
            Label("", id="status_bar"),
            id="topbar"
        )
        yield Container(
            Static("", id="panel_content", markup=True),
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
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        threading.Thread(target=run, daemon=True).start()
        self.map_open = True

    def do_action(self, fn, *args):
        if fn is None:
            self.action_result = "HARDWARE NOT PRESENT -- action locked until uConsole connected"
            return
        ok, msg = fn(*args)
        self.action_result = msg

    def refresh_ui(self):
        d = self.data
        now = datetime.now().strftime("%H:%M:%S")
        gps_s = "GPS:LOCK" if d.gps.fix=="3D" else "GPS:ACQ"
        drone_alert = " [bold red blink]!!DRONE!![/bold red blink]" if any(dr["threat"] in ["MEDIUM","HIGH"] for dr in d.drone.drones) else ""
        open_alert = " [bold red]!!OPEN!![/bold red]" if any(n["enc"]=="OPEN" for n in d.wifi.networks) else ""
        map_s = " [M:ON]" if self.map_open else " [M:MAP]"
        self.query_one("#status_bar", Label).update(
            f"{gps_s}  SDR:ON  BAT:{d.system.battery:.0f}%  {now}{drone_alert}{open_alert}{map_s} ")
        self.query_one("#panel_content", Static).update(self.get_panel())

    def get_panel(self):
        d = self.data
        m = self.current_mode
        ar = self.action_result

        if m == 1:
            open_nets = [n for n in d.wifi.networks if n["enc"]=="OPEN"]
            high_drones = [dr for dr in d.drone.drones if dr["threat"]=="HIGH"]
            alerts = ""
            if open_nets:
                alerts += f"\n  [bold red blink]!! {len(open_nets)} OPEN NETWORK(S) DETECTED !![/bold red blink]"
            if high_drones:
                alerts += f"\n  [bold red blink]!! HIGH THREAT DRONE -- {high_drones[-1]['model']} !![/bold red blink]"
            wifi_spark = sparkline([n["signal"] for n in d.wifi.networks], 30)
            overview_vals = [len(d.drone.drones), len(d.sdr.aircraft), len(d.sdr.hits), len(d.lora.nodes)]
            overview_labs = ["DRONE", "AC", "RF", "LORA"]
            return (
                f"\n"
                f"  {'═'*W}\n"
                f"  GPS: {d.gps.lat:.6f}  {d.gps.lon:.6f}  {d.gps.alt:.0f}m  "
                f"SAT:{d.gps.satellites}  FIX:{d.gps.fix}\n"
                f"  {'═'*W}\n"
                f"  WIFI      {len(d.wifi.networks)} networks  "
                f"({sum(1 for n in d.wifi.networks if n['enc']=='OPEN')} open)\n"
                f"  WIFI SIG  {wifi_spark}\n"
                f"  SDR       {d.sdr.frequency:.1f}MHz  {len(d.sdr.hits)} hits\n"
                f"  AIRCRAFT  {len(d.sdr.aircraft)} detected\n"
                f"  DRONES    {len(d.drone.drones)} detected  "
                f"({sum(1 for dr in d.drone.drones if dr['threat']=='HIGH')} HIGH)\n"
                f"  LORA      {len(d.lora.nodes)} nodes  {len(d.lora.messages)} msgs\n"
                f"  {'═'*W}\n"
                f"  DETECTION COUNT\n"
                f"  {'─'*W}\n"
                f"{vbar_chart(overview_vals, overview_labs, height=6, width=8)}\n"
                f"  {'═'*W}\n"
                f"  STATUS  [bold green]ALL SYSTEMS NOMINAL[/bold green]{alerts}\n"
                f"  press M for live satellite map\n"
                f"  {chr(10033)*W}\n"
                f"  LIVE SIGNAL SPARKLINES\n"
                f"  {chr(9472)*W}\n"
                f"  RF SIG   {sparkline([h['signal'] for h in d.sdr.hits], W-10) if d.sdr.hits else chr(9617)*(W-10)}\n"
                f"  WIFI SIG {sparkline([n['signal'] for n in d.wifi.networks], W-10) if d.wifi.networks else chr(9617)*(W-10)}\n"
                f"  LORA SIG {sparkline([m['rssi'] for m in d.lora.messages], W-10) if d.lora.messages else chr(9617)*(W-10)}\n"
                f"  {chr(10033)*W}\n"
                f"  RECENT AIRCRAFT\n"
                f"  {chr(9472)*W}\n"
                + "".join([f"  ✈ {a['callsign']:<10} {hbar(a['alt'],0,40000,30,'ft','ALT')}  {a['speed']}kts  {a['distance']}km\n" for a in d.sdr.aircraft[-4:]]) +
                f"  {chr(10033)*W}\n"
                f"  RECENT DRONES\n"
                f"  {chr(9472)*W}\n"
                + "".join([f"  {'!!' if dr['threat']=='HIGH' else '▲' if dr['threat']=='MEDIUM' else '◆'} {dr['id']:<10} {dr['model']:<18} {dr['alt']:.0f}m  {dr['distance']:.0f}m  {dr['method']}\n" for dr in d.drone.drones[-3:]]) +
                (f"  no drones\n" if not d.drone.drones else "") +
                f"  {chr(10033)*W}"
            )

        elif m == 2:
            freqs = [315.0, 433.9, 868.0, 915.0, 1090.0]
            freq_counts = {}
            for h in d.sdr.hits:
                f = min(freqs, key=lambda x: abs(x-h["freq"]))
                freq_counts[f] = freq_counts.get(f, 0) + 1
            wf_vals = [freq_counts.get(f, 0) for f in freqs]
            wf_labs = [str(int(f)) for f in freqs]
            sig_spark = sparkline([h["signal"] for h in d.sdr.hits], 50) if d.sdr.hits else "░"*50
            ac = ""
            for a in d.sdr.aircraft[-4:]:
                ac += f"  ✈ {a['callsign']:<10} {hbar(a['alt'],0,40000,20,'ft','ALT')}  {a['speed']}kts  {a['distance']}km\n"
            if not ac:
                ac = "  no aircraft\n"
            hits = ""
            for h in d.sdr.hits[-4:]:
                hits += f"  {h['freq']:>7.1f}MHz  {h['type']:<22} {hbar(h['signal'],-90,-20,15,'dBm','')}\n"
            if not hits:
                hits = "  no hits\n"
            action_line = f"\n  ACTION: {ar}" if ar else ""
            return (
                f"\n"
                f"  {'═'*W}\n"
                f"  SDR  FREQ:{d.sdr.frequency:.3f}MHz  GAIN:{d.sdr.gain}dB\n"
                f"  {hbar(d.sdr.signal_strength,-90,-20,40,'dB','SIG  ')}\n"
                f"  KEYS: T:record IQ  F:FM audio  W:spectrum sweep\n"
                f"  {'═'*W}\n"
                f"  SIGNAL HISTORY\n"
                f"  {sig_spark}\n"
                f"  {'═'*W}\n"
                f"  FREQUENCY HIT COUNT\n"
                f"  {'─'*W}\n"
                f"{vbar_chart(wf_vals, wf_labs, height=5, width=5)}\n"
                f"  {'═'*W}\n"
                f"  AIRCRAFT ({len(d.sdr.aircraft)} detected)\n"
                f"  {'─'*W}\n"
                f"{ac}"
                f"  {'═'*W}\n"
                f"  RF HITS ({len(d.sdr.hits)} decoded)\n"
                f"  {'─'*W}\n"
                f"{hits}"
                f"{action_line}"
            )

        elif m == 3:
            nodes = ""
            rssi_vals = []
            rssi_labs = []
            bat_vals = []
            for n in d.lora.nodes:
                rssi_vals.append(abs(n["rssi"]))
                rssi_labs.append(n["id"][-2:])
                bat_vals.append(n["bat"])
                nodes += f"  {n['id']:<12} {hbar(n['rssi'],-120,-60,25,'dBm','RSSI')}  BAT:{n['bat']}%  {n['temp']}c\n"
            rssi_spark = sparkline([msg["rssi"] for msg in d.lora.messages], 40) if d.lora.messages else "░"*40
            msgs = ""
            for msg in d.lora.messages[-6:]:
                msgs += f"  [{msg['timestamp']}] {msg['node']:<10} {msg['text']}\n"
            if not msgs:
                msgs = "  no messages\n"
            action_line = f"\n  ACTION: {ar}" if ar else ""
            return (
                f"\n"
                f"  {'═'*W}\n"
                f"  LORA MESH  {d.lora.frequency}MHz  {len(d.lora.nodes)} nodes\n"
                f"  KEYS: P:ping node  I:node info\n"
                f"  {'═'*W}\n"
                f"  NODE STATUS\n"
                f"  {'─'*W}\n"
                f"{nodes}"
                f"  NODE SIGNAL\n"
                f"{vbar_chart(rssi_vals, rssi_labs, height=4, width=6)}\n"
                f"  NODE BATTERY\n"
                f"{vbar_chart(bat_vals, rssi_labs, height=4, width=6)}\n"
                f"  RSSI HISTORY\n"
                f"  {rssi_spark}\n"
                f"  {'═'*W}\n"
                f"  MESSAGE LOG\n"
                f"  {'─'*W}\n"
                f"{msgs}"
                f"{action_line}"
            )

        elif m == 4:
            action_line = f"\n  ACTION: {ar}" if ar else ""
            return (
                f"\n"
                f"  {'═'*W}\n"
                f"  WIFI PENTEST  {d.wifi.interface} [{d.wifi.mode}]\n"
                f"  GPS  {d.gps.lat:.6f}  {d.gps.lon:.6f}\n"
                f"  KEYS: UP/DOWN select  A:handshake  D:deauth  S:nmap  C:capture  R:reaver\n"
                f"  {'═'*W}\n"
                f"{wifi_chart(d.wifi.networks, self.selected_network)}"
                f"  {'═'*W}\n"
                f"  HANDSHAKES ({len(d.wifi.handshakes)} captured)\n"
                f"  {'─'*W}\n"
                f"  {'no handshakes' if not d.wifi.handshakes else ''}\n"
                f"  ALL EVENTS LOGGED TO fieldkit.db WITH GPS TAGS"
                f"{action_line}"
            )

        elif m == 5:
            return airspace_chart(d, self.selected_drone, ar)

        elif m == 6:
            return system_chart(d)

    def on_key(self, event: events.Key) -> None:
        d = self.data
        key_map = {"1":1,"2":2,"3":3,"4":4,"5":5,"6":6}

        if event.key in key_map:
            old = self.current_mode
            self.current_mode = key_map[event.key]
            self.query_one(f"#nav{old}", Label).remove_class("active")
            self.query_one(f"#nav{self.current_mode}", Label).add_class("active")
            self.query_one("#mode_label", Label).update(
                f" FIELDKIT OS v1.0 -- {MODES[self.current_mode]} ")
            self.action_result = ""
            self.refresh_ui()

        elif event.key == "m":
            self.open_map()

        elif self.current_mode == 4:
            nets = d.wifi.networks
            if event.key == "up":
                self.selected_network = max(0, self.selected_network-1)
            elif event.key == "down":
                self.selected_network = min(len(nets)-1, self.selected_network+1)
            elif event.key == "a" and nets:
                net = nets[self.selected_network % len(nets)]
                if self.pentest:
                    ok, msg = self.pentest.capture_handshake(
                        net["bssid"], net["ch"], net["ssid"])
                    self.action_result = msg
                else:
                    self.action_result = "HARDWARE NOT PRESENT -- locked until uConsole connected"
            elif event.key == "d" and nets:
                net = nets[self.selected_network % len(nets)]
                if self.pentest:
                    ok, msg = self.pentest.deauth_attack(net["bssid"])
                    self.action_result = msg
                else:
                    self.action_result = "HARDWARE NOT PRESENT -- locked until uConsole connected"
            elif event.key == "s":
                if self.pentest:
                    ok, msg = self.pentest.nmap_scan("192.168.1.0/24")
                    self.action_result = msg
                else:
                    self.action_result = "HARDWARE NOT PRESENT -- locked until uConsole connected"
            elif event.key == "c":
                if self.pentest:
                    ok, msg = self.pentest.packet_capture()
                    self.action_result = msg
                else:
                    self.action_result = "HARDWARE NOT PRESENT -- locked until uConsole connected"
            elif event.key == "r" and nets:
                net = nets[self.selected_network % len(nets)]
                if self.pentest:
                    ok, msg = self.pentest.reaver_attack(net["bssid"])
                    self.action_result = msg
                else:
                    self.action_result = "HARDWARE NOT PRESENT -- locked until uConsole connected"
            self.refresh_ui()

        elif self.current_mode == 2:
            if event.key == "t":
                if self.sdr_actions:
                    ok, msg = self.sdr_actions.tune_and_record(d.sdr.frequency)
                    self.action_result = msg
                else:
                    self.action_result = "HARDWARE NOT PRESENT -- locked until uConsole connected"
            elif event.key == "f":
                if self.sdr_actions:
                    ok, msg = self.sdr_actions.decode_fm(d.sdr.frequency)
                    self.action_result = msg
                else:
                    self.action_result = "HARDWARE NOT PRESENT -- locked until uConsole connected"
            elif event.key == "w":
                if self.sdr_actions:
                    ok, msg = self.sdr_actions.sweep_spectrum()
                    self.action_result = msg
                else:
                    self.action_result = "HARDWARE NOT PRESENT -- locked until uConsole connected"
            self.refresh_ui()

        elif self.current_mode == 5:
            drones = d.drone.drones
            if event.key == "up":
                self.selected_drone = max(0, self.selected_drone-1)
            elif event.key == "down":
                self.selected_drone = min(max(0,len(drones)-1), self.selected_drone+1)
            elif event.key == "t" and drones:
                dr = drones[self.selected_drone % len(drones)]
                if self.airspace_actions:
                    ok, msg = self.airspace_actions.tag_drone(dr["id"])
                    self.action_result = msg
                else:
                    self.action_result = "HARDWARE NOT PRESENT -- locked until uConsole connected"
            elif event.key == "e":
                if self.airspace_actions:
                    ok, msg = self.airspace_actions.export_report(d.gps.lat, d.gps.lon)
                    self.action_result = msg
                else:
                    self.action_result = "HARDWARE NOT PRESENT -- locked until uConsole connected"
            self.refresh_ui()

        elif self.current_mode == 3:
            if event.key == "p":
                nodes = d.lora.nodes
                if nodes and self.mesh:
                    ok, msg = self.mesh.ping_node(nodes[0]["id"])
                    self.action_result = msg
                else:
                    self.action_result = "HARDWARE NOT PRESENT -- locked until uConsole connected"
            elif event.key == "i":
                if self.mesh:
                    ok, msg = self.mesh.get_node_info()
                    self.action_result = msg
                else:
                    self.action_result = "HARDWARE NOT PRESENT -- locked until uConsole connected"
            self.refresh_ui()

if __name__ == "__main__":
    app = FieldKit()
    app.run()

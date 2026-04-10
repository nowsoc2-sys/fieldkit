from textual.app import App, ComposeResult
from textual.widgets import Static, Label
from textual.containers import Container, Horizontal, Vertical
from textual import events
from fieldkit_data import FieldKitData
from datetime import datetime
import math
import json
import os
import subprocess
import threading
import plotext as plt
import io

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
"""

MODES = {1:"RECON",2:"SDR",3:"MESH",4:"PENTEST",5:"AIRSPACE",6:"SYSTEM"}
W = 76

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
    if not values:
        return "  no data\n"
    mx = max(values) if max(values) > 0 else 1
    lines = []
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
    for row in range(height):
        line = "  "
        for i, col in enumerate(bars):
            cell = col[row]
            line += f" {cell*width} "
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
    low_bar = "◆"*low
    med_bar = "▲"*med
    high_bar = "!!"*high if high else ""
    ring = f"  [LOW:{low_bar if low else '-'}] [MED:{med_bar if med else '-'}] [HIGH:{high_bar if high else '-'}]"
    pct_high = (high/total)*100 if total > 0 else 0
    threat_bar = hbar(pct_high, 0, 100, 20, "%", "THREAT")
    return ring + "\n  " + threat_bar

def signal_history_chart(hits, width=50, height=5):
    if not hits:
        return "  no signal history\n"
    sigs = [h["signal"] for h in hits[-width:]]
    spark = sparkline(sigs, width)
    lo = min(sigs) if sigs else -90
    hi = max(sigs) if sigs else -30
    lines = []
    lines.append(f"  SIGNAL HISTORY  min:{lo:.0f}dBm  max:{hi:.0f}dBm")
    lines.append(f"  {spark}")
    bar_vals = []
    bar_labs = []
    freqs = {}
    for h in hits:
        f = str(h["freq"])
        freqs[f] = freqs.get(f, [])
        freqs[f].append(h["signal"])
    for f, sigs in list(freqs.items())[-6:]:
        avg = sum(sigs)/len(sigs)
        bar_vals.append(abs(avg))
        bar_labs.append(f[:5])
    lines.append(vbar_chart(bar_vals, bar_labs, height=5, width=4))
    return "\n".join(lines)

def wifi_chart(networks):
    if not networks:
        return "  no networks\n"
    lines = []
    lines.append("  SIGNAL STRENGTH BY NETWORK")
    lines.append("")
    for n in networks:
        sig = n["signal"]
        pct = min(1.0, max(0.0, (sig+100)/70))
        width = 35
        f = int(pct*width)
        if n["enc"] == "OPEN":
            fill = "█"*f
            label_suffix = " !! OPEN !!"
            bar_char = "!"
        else:
            fill = "▓"*f
            label_suffix = ""
            bar_char = " "
        bar = f"[{fill}{'░'*(width-f)}]"
        enc_color = "OPEN" if n["enc"]=="OPEN" else n["enc"]
        lines.append(f"  {n['ssid'][:22]:<22} {bar} {sig}dBm {label_suffix}")
        ch_spark = "ch" + str(n["ch"])
        lines.append(f"  {'':22} {enc_color:<5} {ch_spark}")
        lines.append("")
    return "\n".join(lines)

def system_chart(d):
    cpu = d.system.cpu
    ram_pct = (d.system.ram_used/d.system.ram_total)*100
    temp = d.system.temp
    bat = d.system.battery
    up = f"{d.system.uptime//3600:02d}:{(d.system.uptime%3600)//60:02d}:{d.system.uptime%60:02d}"

    lines = []
    lines.append(f"  {'═'*W}")
    lines.append(f"  SYSTEM TELEMETRY  //  UPTIME: {up}")
    lines.append(f"  {'─'*W}")
    lines.append(f"  {hbar(cpu, 0, 100, 40, '%', 'CPU   ')}")
    lines.append(f"  {hbar(ram_pct, 0, 100, 40, '%', 'RAM   ')}  {d.system.ram_used:.1f}/{d.system.ram_total:.0f}GB")
    lines.append(f"  {hbar(temp, 20, 90, 40, 'c', 'TEMP  ')}")
    lines.append(f"  {hbar(bat, 0, 100, 40, '%', 'BAT   ')}")
    lines.append(f"  {'═'*W}")
    lines.append(f"  VERTICAL TREND  (last 10 readings)")
    lines.append(f"  {'─'*W}")

    height = 6
    metrics = [
        ("CPU", cpu, 0, 100),
        ("RAM", ram_pct, 0, 100),
        ("TEMP", temp, 20, 90),
        ("BAT", bat, 0, 100),
    ]
    col_w = 12
    for row in range(height, -1, -1):
        line = "  "
        for label, val, lo, hi in metrics:
            pct = min(1.0, max(0.0, (val-lo)/(hi-lo)))
            h = int(pct*height)
            if row == 0:
                line += f"{'─'*col_w}  "
            elif row <= h:
                if h > height*0.8:
                    line += f"{'█'*col_w}  "
                elif h > height*0.5:
                    line += f"{'▓'*col_w}  "
                else:
                    line += f"{'▒'*col_w}  "
            else:
                line += f"{'░'*col_w}  "
        lines.append(line)
    val_line = "  "
    for label, val, lo, hi in metrics:
        val_line += f"{label}:{val:.0f}{'%' if label!='TEMP' else 'c'}  ".ljust(col_w+2)
    lines.append(val_line)
    lines.append(f"  {'═'*W}")
    sdr = "[LIVE]" if d.system.sdr_on else "[SIM] "
    gps = "[LIVE]" if d.system.gps_on else "[SIM] "
    lora = "[LIVE]" if d.system.lora_on else "[SIM] "
    lines.append(f"  SDR:{sdr}  GPS:{gps}  LORA:{lora}")
    lines.append(f"  {'─'*W}")
    lines.append(f"  STACK: dump1090  rtl_433  DroneSecurity  Kismet  Meshtastic  gpsd")
    lines.append(f"  DB: fieldkit.db  //  FIELDKIT OS v1.0  //  NWS-C")
    return "\n".join(lines)

def airspace_chart(d):
    drones = d.drone.drones
    aircraft = d.sdr.aircraft
    lines = []
    lines.append(f"  {'═'*W}")
    lines.append(f"  AIRSPACE MONITOR  //  DRONE-ID:ON  REMOTE-ID:ON  ADS-B:ON")
    lines.append(f"  {'─'*W}")
    lines.append(f"  THREAT OVERVIEW")
    lines.append(threat_ring(drones))
    lines.append(f"  {'═'*W}")

    if drones:
        lines.append(f"  DRONES ({len(drones)} detected)")
        lines.append(f"  {'─'*W}")
        dist_vals = []
        dist_labs = []
        for dr in drones[-5:]:
            icon = {"LOW":"◆","MEDIUM":"▲","HIGH":"!!"}.get(dr["threat"],"?")
            dist_bar = hbar(min(dr["distance"],2000), 0, 2000, 20, "m", "DIST ")
            lines.append(f"  {icon} {dr['id']:<10} {dr['model']:<16} ALT:{dr['alt']:>4.0f}m")
            lines.append(f"    {dist_bar}  METHOD:{dr['method']}")
            dist_vals.append(dr["distance"])
            dist_labs.append(dr["id"][-4:])
        lines.append("")
        lines.append(f"  DRONE DISTANCE CHART")
        lines.append(vbar_chart(dist_vals, dist_labs, height=4, width=5))

    lines.append(f"  {'═'*W}")

    if aircraft:
        lines.append(f"  AIRCRAFT ({len(aircraft)} detected via ADS-B 1090MHz)")
        lines.append(f"  {'─'*W}")
        alt_vals = []
        alt_labs = []
        for a in aircraft[-5:]:
            alt_bar = hbar(a["alt"], 0, 40000, 25, "ft", "ALT  ")
            lines.append(f"  ✈ {a['callsign']:<10} {alt_bar}  {a['speed']}kts  {a['distance']}km")
            alt_vals.append(a["alt"])
            alt_labs.append(a["callsign"][:5])
        lines.append("")
        lines.append(f"  ALTITUDE CHART")
        lines.append(vbar_chart(alt_vals, alt_labs, height=4, width=5))

    lines.append(f"  {'═'*W}")
    lines.append(f"  THREAT ALERTS")
    lines.append(f"  {'─'*W}")
    alerts = d.drone.alerts[-4:] if d.drone.alerts else ["  no alerts"]
    for al in alerts:
        lines.append(f"  {al}")

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
        with open(os.path.expanduser("~/fieldkit_live.json"),"w") as f:
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
        self.action_result = ""
        self.selected_network = 0
        self.selected_drone = 0
        from fieldkit_actions import (
            PENTEST, SDR, AIRSPACE, MESH, check_action_hardware)
        self.pentest = PENTEST
        self.sdr_actions = SDR
        self.airspace = AIRSPACE
        self.mesh = MESH
        check_action_hardware()

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
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        threading.Thread(target=run, daemon=True).start()
        self.map_open = True

    def refresh_ui(self):
        d = self.data
        now = datetime.now().strftime("%H:%M:%S")
        bat = f"BAT:{d.system.battery:.0f}%"
        gps_s = "GPS:LOCK" if d.gps.fix=="3D" else "GPS:ACQ"
        drone_alert = " !!DRONE!!" if any(dr["threat"] in ["MEDIUM","HIGH"] for dr in d.drone.drones) else ""
        open_alert = " !!OPEN!!" if any(n["enc"]=="OPEN" for n in d.wifi.networks) else ""
        map_s = " [M:ON]" if self.map_open else " [M:MAP]"
        self.query_one("#status_bar", Label).update(
            f"{gps_s}  SDR:ON  {bat}  {now}{drone_alert}{open_alert}{map_s} ")
        self.query_one("#panel_content", Static).update(self.get_panel())

    def get_panel(self):
        d = self.data
        m = self.current_mode

        if m == 1:
            open_nets = [n for n in d.wifi.networks if n["enc"]=="OPEN"]
            high_drones = [dr for dr in d.drone.drones if dr["threat"]=="HIGH"]
            alerts = ""
            if open_nets:
                alerts += f"\n  !! {len(open_nets)} OPEN NETWORK(S) DETECTED !!"
            if high_drones:
                alerts += f"\n  !! HIGH THREAT DRONE -- {high_drones[-1]['model']} !!"

            all_sigs = [n["signal"] for n in d.wifi.networks]
            wifi_spark = sparkline(all_sigs, 30) if all_sigs else "░"*30

            drone_count = len(d.drone.drones)
            ac_count = len(d.sdr.aircraft)
            hit_count = len(d.sdr.hits)

            overview_vals = [drone_count, ac_count, hit_count, len(d.lora.nodes)]
            overview_labs = ["DRONE", "AC", "RF", "LORA"]

            return (
                f"\n"
                f"  {'═'*W}\n"
                f"  GPS: {d.gps.lat:.6f}  {d.gps.lon:.6f}  {d.gps.alt:.0f}m  "
                f"SAT:{d.gps.satellites}  FIX:{d.gps.fix}  SPD:{d.gps.speed:.1f}km/h\n"
                f"  {'═'*W}\n"
                f"  ENVIRONMENT OVERVIEW\n"
                f"  {'─'*W}\n"
                f"  WIFI      {len(d.wifi.networks)} networks  ({sum(1 for n in d.wifi.networks if n['enc']=='OPEN')} open)\n"
                f"  WIFI SIG  {wifi_spark}\n"
                f"  SDR       {d.sdr.frequency:.1f}MHz  {hit_count} RF hits decoded\n"
                f"  AIRCRAFT  {ac_count} detected via ADS-B\n"
                f"  DRONES    {drone_count} detected  ({sum(1 for dr in d.drone.drones if dr['threat']=='HIGH')} HIGH threat)\n"
                f"  LORA      {len(d.lora.nodes)} nodes  {len(d.lora.messages)} messages\n"
                f"  {'═'*W}\n"
                f"  DETECTION COUNT CHART\n"
                f"  {'─'*W}\n"
                f"{vbar_chart(overview_vals, overview_labs, height=6, width=8)}\n"
                f"  {'═'*W}\n"
                f"  STATUS   ALL SYSTEMS NOMINAL{alerts}\n"
                f"  press M for live satellite map"
            )

        elif m == 2:
            freqs = [315.0, 433.9, 868.0, 915.0, 1090.0]
            freq_counts = {}
            freq_sigs = {}
            for h in d.sdr.hits:
                f = min(freqs, key=lambda x: abs(x-h["freq"]))
                freq_counts[f] = freq_counts.get(f, 0) + 1
                freq_sigs.setdefault(f, []).append(h["signal"])
            wf_vals = [freq_counts.get(f, 0) for f in freqs]
            wf_labs = [str(f) for f in freqs]
            sig_spark = sparkline([h["signal"] for h in d.sdr.hits], 50) if d.sdr.hits else "░"*50
            ac = ""
            for a in d.sdr.aircraft[-4:]:
                alt_bar = hbar(a["alt"], 0, 40000, 20, "ft", "ALT")
                ac += f"  ✈ {a['callsign']:<10} {alt_bar}  {a['speed']}kts  {a['distance']}km\n"
            if not ac:
                ac = "  no aircraft detected\n"
            hits = ""
            for h in d.sdr.hits[-4:]:
                hits += f"  {h['freq']:>7.1f}MHz  {h['type']:<22} {hbar(h['signal'],-90,-20,15,'dBm','')}\n"
            if not hits:
                hits = "  no hits decoded\n"
            return (
                f"\n"
                f"  {'═'*W}\n"
                f"  SDR  FREQ:{d.sdr.frequency:.3f}MHz  GAIN:{d.sdr.gain}dB\n"
                f"  {hbar(d.sdr.signal_strength,-90,-20,40,'dB','SIG  ')}\n"
                f"  {'═'*W}\n"
                f"  SIGNAL HISTORY (last {len(d.sdr.hits)} hits)\n"
                f"  {'─'*W}\n"
                f"  {sig_spark}\n"
                f"  {'═'*W}\n"
                f"  FREQUENCY HIT COUNT\n"
                f"  {'─'*W}\n"
                f"{vbar_chart(wf_vals, wf_labs, height=5, width=5)}\n"
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
            rssi_vals = []
            rssi_labs = []
            bat_vals = []
            for n in d.lora.nodes:
                rssi_vals.append(abs(n["rssi"]))
                rssi_labs.append(n["id"][-2:])
                bat_vals.append(n["bat"])
                nodes += f"  {n['id']:<12} {hbar(n['rssi'],-120,-60,25,'dBm','RSSI')}  BAT:{n['bat']}%  {n['temp']}c\n"
            rssi_spark = sparkline([m["rssi"] for m in d.lora.messages], 40) if d.lora.messages else "░"*40
            msgs = ""
            for msg in d.lora.messages[-6:]:
                msgs += f"  [{msg['timestamp']}] {msg['node']:<10} {msg['text']}\n"
            if not msgs:
                msgs = "  no messages\n"
            return (
                f"\n"
                f"  {'═'*W}\n"
                f"  LORA MESH  {d.lora.frequency}MHz  {len(d.lora.nodes)} nodes  {len(d.lora.messages)} messages\n"
                f"  {'═'*W}\n"
                f"  NODE STATUS\n"
                f"  {'─'*W}\n"
                f"{nodes}"
                f"  {'─'*W}\n"
                f"  NODE SIGNAL CHART\n"
                f"{vbar_chart(rssi_vals, rssi_labs, height=4, width=6)}\n"
                f"  BATTERY CHART\n"
                f"{vbar_chart(bat_vals, rssi_labs, height=4, width=6)}\n"
                f"  RSSI HISTORY\n"
                f"  {rssi_spark}\n"
                f"  {'═'*W}\n"
                f"  MESSAGE LOG\n"
                f"  {'─'*W}\n"
                f"{msgs}"
            )

        elif m == 4:
            return (
                f"\n"
                f"  {'═'*W}\n"
                f"  WIFI PENTEST  {d.wifi.interface} [{d.wifi.mode}]\n"
                f"  GPS  {d.gps.lat:.6f}  {d.gps.lon:.6f}\n"
                f"  {'═'*W}\n"
                f"{wifi_chart(d.wifi.networks)}"
                f"  {'═'*W}\n"
                f"  HANDSHAKES ({len(d.wifi.handshakes)} captured)\n"
                f"  {'─'*W}\n"
                f"  {'no handshakes captured' if not d.wifi.handshakes else ''}\n"
                f"  ALL EVENTS LOGGED TO fieldkit.db WITH GPS TAGS"
            )

        elif m == 5:
            return airspace_chart(d)

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
            if event.key == "a" and nets:
                net = nets[self.selected_network % len(nets)]
                ok, msg = self.pentest.capture_handshake(
                    net["bssid"], net["ch"], net["ssid"])
                self.action_result = msg
            elif event.key == "d" and nets:
                net = nets[self.selected_network % len(nets)]
                ok, msg = self.pentest.deauth_attack(net["bssid"])
                self.action_result = msg
            elif event.key == "s" and nets:
                ok, msg = self.pentest.nmap_scan("192.168.1.0/24")
                self.action_result = msg
            elif event.key == "c":
                ok, msg = self.pentest.packet_capture()
                self.action_result = msg
            elif event.key == "r" and nets:
                net = nets[self.selected_network % len(nets)]
                ok, msg = self.pentest.reaver_attack(net["bssid"])
                self.action_result = msg
            elif event.key == "up":
                self.selected_network = max(0, self.selected_network - 1)
            elif event.key == "down":
                self.selected_network = min(
                    len(nets)-1, self.selected_network + 1)
        elif self.current_mode == 2:
            if event.key == "t":
                ok, msg = self.sdr_actions.tune_and_record(
                    d.sdr.frequency)
                self.action_result = msg
            elif event.key == "f":
                ok, msg = self.sdr_actions.decode_fm(d.sdr.frequency)
                self.action_result = msg
            elif event.key == "w":
                ok, msg = self.sdr_actions.sweep_spectrum()
                self.action_result = msg
        elif self.current_mode == 5:
            drones = d.drone.drones
            if event.key == "t" and drones:
                dr = drones[self.selected_drone % len(drones)]
                ok, msg = self.airspace.tag_drone(dr["id"])
                self.action_result = msg
            elif event.key == "e":
                ok, msg = self.airspace.export_report(
                    d.gps.lat, d.gps.lon)
                self.action_result = msg
            elif event.key == "up":
                self.selected_drone = max(0, self.selected_drone - 1)
            elif event.key == "down":
                self.selected_drone = min(
                    len(drones)-1, self.selected_drone + 1)
        elif self.current_mode == 3:
            if event.key == "p":
                nodes = d.lora.nodes
                if nodes:
                    ok, msg = self.mesh.ping_node(nodes[0]["id"])
                    self.action_result = msg
            elif event.key == "i":
                ok, msg = self.mesh.get_node_info()
                self.action_result = msg
        self.refresh_ui()
        elif event.key == "m":
            self.open_map()

if __name__ == "__main__":
    app = FieldKit()
    app.run()


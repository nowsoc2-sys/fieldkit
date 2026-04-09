from textual.app import App, ComposeResult
from textual.widgets import Static, Label
from textual.containers import Container, Horizontal
from textual import events
from fieldkit_data import FieldKitData
from datetime import datetime
import math

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

def bar(val, lo, hi, width=20, unit=""):
    pct = min(1.0, max(0.0, (val - lo) / (hi - lo)))
    f = int(pct * width)
    return f"[{'█'*f}{'░'*(width-f)}] {val:.1f}{unit}"

def threat_color(level):
    return {"LOW": "◆", "MEDIUM": "▲", "HIGH": "!!"}.get(level, "?")

def ascii_radar(aircraft, drones, radius=18, width=40, height=20):
    grid = [[" " for _ in range(width*2)] for _ in range(height)]
    cx, cy = width, height // 2

    for r_pct in [0.33, 0.66, 1.0]:
        r = int(radius * r_pct)
        for angle in range(0, 360, 3):
            rad = math.radians(angle)
            x = int(cx + r * math.sin(rad))
            y = int(cy - int(r * 0.45 * math.cos(rad)))
            if 0 <= y < height and 0 <= x < width*2:
                grid[y][x] = "·"

    for angle in range(0, 360, 90):
        rad = math.radians(angle)
        for step in range(1, radius+1):
            x = int(cx + step * math.sin(rad))
            y = int(cy - int(step * 0.45 * math.cos(rad)))
            if 0 <= y < height and 0 <= x < width*2:
                grid[y][x] = "·"

    if 0 <= cy < height:
        grid[cy][cx] = "+"
    if cy-1 >= 0 and cx < width*2:
        grid[cy-1][cx-1] = "N"
    if cy+1 < height and cx < width*2:
        grid[cy+1][cx-1] = "S"
    if cy < height and cx-radius-1 >= 0:
        grid[cy][cx-radius-1] = "W"
    if cy < height and cx+radius+1 < width*2:
        grid[cy][cx+radius+1] = "E"

    for a in aircraft:
        bearing = random_bearing(a.get("callsign", ""))
        dist_pct = min(1.0, a.get("distance", 100) / 250.0)
        r = int(dist_pct * radius)
        rad = math.radians(bearing)
        x = int(cx + r * math.sin(rad))
        y = int(cy - int(r * 0.45 * math.cos(rad)))
        if 0 <= y < height and 0 <= x < width*2-1:
            grid[y][x] = "✈"

    for d in drones:
        bearing = random_bearing(d.get("id", ""))
        dist_pct = min(1.0, d.get("distance", 500) / 2000.0)
        r = int(dist_pct * radius)
        rad = math.radians(bearing)
        x = int(cx + r * math.sin(rad))
        y = int(cy - int(r * 0.45 * math.cos(rad)))
        if 0 <= y < height and 0 <= x < width*2-1:
            symbol = "!!" if d.get("threat") == "HIGH" else "◆"
            grid[y][x] = symbol[0]

    lines = []
    for row in grid:
        lines.append("  " + "".join(row))
    return "\n".join(lines)

def random_bearing(seed_str):
    val = sum(ord(c) for c in seed_str) if seed_str else 0
    return (val * 37) % 360

def waterfall(hits, width=60, rows=5):
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
                if f == 1090.0 and matching:
                    char = "▲"
            else:
                intensity = max(0, 0.15 - row * 0.03)
                char = "░" if intensity > 0.05 else " "
            line += f"   {char}{char}{char}    "
        lines.append(line)

    lines.append("  " + "─" * (len(freqs) * 9))
    return "\n".join(lines)

def signal_compass(nodes, width=40, height=10):
    cx, cy = width, height // 2
    grid = [[" " for _ in range(width*2)] for _ in range(height)]

    for r in [4, 8]:
        for angle in range(0, 360, 5):
            rad = math.radians(angle)
            x = int(cx + r * 2 * math.sin(rad))
            y = int(cy - int(r * math.cos(rad)))
            if 0 <= y < height and 0 <= x < width*2:
                grid[y][x] = "·"

    if 0 <= cy < height:
        grid[cy][cx] = "◉"

    for i, node in enumerate(nodes):
        bearing = (i * 120 + 45) % 360
        rssi = node.get("rssi", -90)
        dist = min(8, max(2, int(abs(rssi) / 12)))
        rad = math.radians(bearing)
        x = int(cx + dist * 2 * math.sin(rad))
        y = int(cy - int(dist * math.cos(rad)))
        if 0 <= y < height and 0 <= x < width*2-2:
            label = node["id"][-2:]
            grid[y][x] = "N"
            if x+1 < width*2:
                grid[y][x+1] = label[0] if label else "?"

    lines = []
    for row in grid:
        lines.append("  " + "".join(row))
    return "\n".join(lines)

class FieldKit(App):
    CSS = CSS
    current_mode = 1
    sweep_angle = 0

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
        self.sweep_angle = (self.sweep_angle + 15) % 360
        self.refresh_ui()

    def refresh_ui(self):
        d = self.data
        now = datetime.now().strftime("%H:%M:%S")
        bat = f"BAT:{d.system.battery:.0f}%"
        gps_s = "GPS:LOCK" if d.gps.fix == "3D" else "GPS:ACQ"
        drone_alert = " !!DRONE!!" if any(dr["threat"] in ["MEDIUM","HIGH"] for dr in d.drone.drones) else ""
        open_alert = " !!OPEN NET!!" if any(n["enc"]=="OPEN" for n in d.wifi.networks) else ""
        self.query_one("#status_bar", Label).update(
            f"{gps_s}  SDR:ON  {bat}  {now}{drone_alert}{open_alert} ")
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

            radar = ascii_radar(d.sdr.aircraft, d.drone.drones)

            summary = (
                f"\n"
                f"  {'═'*W}\n"
                f"  GPS: {d.gps.lat:.5f}  {d.gps.lon:.5f}  {d.gps.alt:.0f}m  SAT:{d.gps.satellites}  {d.gps.fix}\n"
                f"  {'─'*W}\n"
                f"  WIFI:{len(d.wifi.networks)}({sum(1 for n in d.wifi.networks if n['enc']=='OPEN')} open)  "
                f"SDR:{len(d.sdr.hits)} hits  "
                f"AIRCRAFT:{len(d.sdr.aircraft)}  "
                f"DRONES:{len(d.drone.drones)}  "
                f"LORA:{len(d.lora.nodes)} nodes\n"
                f"  {'═'*W}\n"
                f"  RADAR  [◆=drone  ✈=aircraft  ·=range rings  +=you]\n"
                f"  {'─'*W}\n"
            )
            return summary + radar + f"\n  {'═'*W}\n  STATUS  ALL SYSTEMS NOMINAL{alerts}"

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
            compass = signal_compass(d.lora.nodes)
            nodes = ""
            for n in d.lora.nodes:
                nodes += f"  {n['id']:<12} {bar(n['rssi'],-120,-60,15,'dBm')}  BAT:{n['bat']}%  {n['temp']}c\n"
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
                f"  NODE COMPASS  [◉=you  N=node]\n"
                f"  {'─'*W}\n"
                f"{compass}\n"
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
                sig_bar = bar(n['signal'], -100, -30, 15, 'dBm')
                nets += f"  {n['ssid']:<26} {n['enc']:<5} ch{n['ch']:<3} {sig_bar}{flag}\n"

            net_chart = ""
            net_chart += "  SIGNAL STRENGTH\n  "
            for n in d.wifi.networks:
                pct = min(1.0, max(0.0, (n['signal'] + 100) / 70))
                h = int(pct * 6)
                net_chart += f" {'█'*h}{'░'*(6-h)} "
            net_chart += "\n  "
            for n in d.wifi.networks:
                label = n['ssid'][:6]
                net_chart += f" {label:<8}"

            hs = "  no handshakes captured\n" if not d.wifi.handshakes else ""
            return (
                f"\n"
                f"  {'═'*W}\n"
                f"  WIFI PENTEST  {d.wifi.interface} [{d.wifi.mode}]  GPS:{d.gps.lat:.5f},{d.gps.lon:.5f}\n"
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
            radar = ascii_radar(d.sdr.aircraft, d.drone.drones)
            drones = ""
            for dr in d.drone.drones[-3:]:
                icon = threat_color(dr["threat"])
                drones += f"  {icon} {dr['id']:<10} {dr['model']:<18} {dr['alt']:>4.0f}m  {dr['distance']:>5.0f}m  {dr['method']}\n"
            if not drones:
                drones = "  no drones detected\n"
            aircraft = ""
            for a in d.sdr.aircraft[-3:]:
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
                f"  {'─'*W}\n"
                f"  [◆=drone LOW  ▲=MEDIUM  !!=HIGH  ✈=aircraft  +=you]\n"
                f"{radar}\n"
                f"  {'═'*W}\n"
                f"  DRONES ({len(d.drone.drones)})          AIRCRAFT ({len(d.sdr.aircraft)})\n"
                f"  {'─'*W}\n"
                f"{drones}"
                f"{aircraft}"
                f"  {'═'*W}\n"
                f"  ALERTS\n"
                f"  {'─'*W}\n"
                f"{alerts}"
            )

        elif m == 6:
            up = f"{d.system.uptime//3600:02d}:{(d.system.uptime%3600)//60:02d}:{d.system.uptime%60:02d}"
            cpu_h = int((d.system.cpu / 100) * 10)
            ram_h = int(((d.system.ram_used/d.system.ram_total)) * 10)
            temp_h = int(((d.system.temp-20) / 60) * 10)
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

if __name__ == "__main__":
    app = FieldKit()
    app.run()

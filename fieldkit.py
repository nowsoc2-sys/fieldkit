from textual.app import App, ComposeResult
from textual.widgets import Static, Label
from textual.containers import Container, Horizontal
from textual import events
from fieldkit_data import FieldKitData
from datetime import datetime

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

def threat_icon(level):
    return {"LOW": "◆", "MEDIUM": "▲", "HIGH": "!!"}. get(level, "?")

def spectrum(hits, width=60):
    freqs = [315.0, 433.9, 868.0, 915.0]
    l1 = "  "
    l2 = "  "
    for f in freqs:
        m = [h for h in hits if abs(h["freq"] - f) < 1]
        sig = max([h["signal"] for h in m]) if m else -90
        pct = min(1.0, max(0.0, (sig + 90) / 60))
        b = int(pct * 6)
        l1 += f" {f:>6.1f}MHz "
        l2 += f" {'█'*b}{'░'*(6-b)}     "
    return l1 + "\n" + l2

class FieldKit(App):
    CSS = CSS
    current_mode = 1

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
                alerts += f"\n  !! HIGH THREAT DRONE DETECTED -- {high_drones[-1]['model']} !!"
            return (
                f"\n"
                f"  {'═'*W}\n"
                f"  GPS POSITION\n"
                f"  {'─'*W}\n"
                f"  LAT    {d.gps.lat:.6f}     LON    {d.gps.lon:.6f}\n"
                f"  ALT    {d.gps.alt:.0f}m               SAT    {d.gps.satellites} / FIX:{d.gps.fix}\n"
                f"  SPEED  {d.gps.speed:.1f} km/h\n"
                f"  {'═'*W}\n"
                f"  ENVIRONMENT SUMMARY\n"
                f"  {'─'*W}\n"
                f"  WIFI     {len(d.wifi.networks)} networks  ({sum(1 for n in d.wifi.networks if n['enc']=='OPEN')} open)\n"
                f"  SDR      {d.sdr.frequency:.1f} MHz  {len(d.sdr.hits)} RF hits\n"
                f"  AIRCRAFT {len(d.sdr.aircraft)} detected via ADS-B\n"
                f"  DRONES   {len(d.drone.drones)} detected  ({sum(1 for dr in d.drone.drones if dr['threat']=='HIGH')} HIGH threat)\n"
                f"  LORA     {len(d.lora.nodes)} nodes  {len(d.lora.messages)} messages\n"
                f"  {'═'*W}\n"
                f"  STATUS   ALL SYSTEMS NOMINAL{alerts}"
            )

        elif m == 2:
            ac = ""
            for a in d.sdr.aircraft[-4:]:
                ac += f"  {a['callsign']:<10} {a['alt']:>6}ft  {a['speed']:>3}kts  {a['heading']:>3}°  {a['distance']:>7.1f}km\n"
            if not ac:
                ac = "  no aircraft detected\n"
            hits = ""
            for h in d.sdr.hits[-4:]:
                hits += f"  {h['freq']:>7.1f}MHz  {h['type']:<22} {h['signal']:>6.1f}dBm\n"
            if not hits:
                hits = "  no hits decoded\n"
            return (
                f"\n"
                f"  {'═'*W}\n"
                f"  SDR RECEIVER\n"
                f"  {'─'*W}\n"
                f"  FREQ   {d.sdr.frequency:.3f} MHz    GAIN   {d.sdr.gain} dB\n"
                f"  SIGNAL {bar(d.sdr.signal_strength, -90, -20, 25, 'dB')}\n"
                f"  {'═'*W}\n"
                f"  SPECTRUM\n"
                f"  {'─'*W}\n"
                f"{spectrum(d.sdr.hits)}\n"
                f"  {'═'*W}\n"
                f"  AIRCRAFT ADS-B 1090MHz ({len(d.sdr.aircraft)} detected)\n"
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
                nodes += f"  {n['id']:<12} {bar(n['rssi'], -120, -60, 12, 'dBm')}  BAT:{n['bat']}%  {n['temp']}c\n"
            msgs = ""
            for msg in d.lora.messages[-8:]:
                msgs += f"  [{msg['timestamp']}] {msg['node']:<10} {msg['text']}\n"
            if not msgs:
                msgs = "  no messages\n"
            return (
                f"\n"
                f"  {'═'*W}\n"
                f"  LORA MESH  --  {d.lora.frequency} MHz\n"
                f"  {'─'*W}\n"
                f"  {len(d.lora.nodes)} NODES VISIBLE  //  {len(d.lora.messages)} MESSAGES RECEIVED\n"
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
                nets += f"  {n['ssid']:<28} {n['enc']:<5} ch{n['ch']:<2} {bar(n['signal'],-100,-30,12,'dBm')}{flag}\n"
            hs = "  no handshakes captured\n" if not d.wifi.handshakes else ""
            return (
                f"\n"
                f"  {'═'*W}\n"
                f"  WIFI PENTEST  --  {d.wifi.interface} [{d.wifi.mode}]\n"
                f"  {'─'*W}\n"
                f"  GPS  {d.gps.lat:.6f}  {d.gps.lon:.6f}  (all detections tagged)\n"
                f"  {'═'*W}\n"
                f"  NETWORKS IN RANGE ({len(d.wifi.networks)})\n"
                f"  {'─'*W}\n"
                f"{nets}"
                f"  {'═'*W}\n"
                f"  HANDSHAKES ({len(d.wifi.handshakes)} captured)\n"
                f"  {'─'*W}\n"
                f"{hs}"
                f"  ALL EVENTS LOGGED TO fieldkit.db WITH GPS COORDINATES"
            )

        elif m == 5:
            drones = ""
            for dr in d.drone.drones[-4:]:
                icon = threat_icon(dr["threat"])
                drones += f"  {icon} {dr['id']:<12} {dr['model']:<20} {dr['alt']:>5.0f}m  {dr['distance']:>6.0f}m away\n"
                drones += f"    METHOD:{dr['method']:<18} THREAT:{dr['threat']}\n"
            if not drones:
                drones = "  no drones detected\n"
            aircraft = ""
            for a in d.sdr.aircraft[-3:]:
                aircraft += f"  ✈ {a['callsign']:<10} {a['alt']:>6}ft  {a['speed']:>3}kts  {a['distance']:>7.1f}km\n"
            if not aircraft:
                aircraft = "  no aircraft detected\n"
            alerts = ""
            for al in d.drone.alerts[-4:]:
                alerts += f"  {al}\n"
            if not alerts:
                alerts = "  no alerts\n"
            return (
                f"\n"
                f"  {'═'*W}\n"
                f"  AIRSPACE MONITOR\n"
                f"  {'─'*W}\n"
                f"  DRONE-ID: {'ACTIVE' if d.drone.droneid_active else 'OFF'}  "
                f"REMOTE-ID: {'ACTIVE' if d.drone.remote_id_active else 'OFF'}  "
                f"ADS-B: ACTIVE\n"
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
            sdr = "[ON] " if d.system.sdr_on else "[OFF]"
            gps = "[ON] " if d.system.gps_on else "[OFF]"
            lora = "[ON] " if d.system.lora_on else "[OFF]"
            return (
                f"\n"
                f"  {'═'*W}\n"
                f"  SYSTEM STATUS\n"
                f"  {'─'*W}\n"
                f"  CPU     {bar(d.system.cpu, 0, 100, 25, '%')}\n"
                f"  RAM     {bar((d.system.ram_used/d.system.ram_total)*100, 0, 100, 25, '%')}  {d.system.ram_used:.1f}/{d.system.ram_total:.0f}GB\n"
                f"  TEMP    {bar(d.system.temp, 20, 80, 25, 'c')}\n"
                f"  BAT     {bar(d.system.battery, 0, 100, 25, '%')}\n"
                f"  UPTIME  {up}\n"
                f"  {'═'*W}\n"
                f"  MODULES\n"
                f"  {'─'*W}\n"
                f"  SDR {sdr}  GPS {gps}  LORA {lora}\n"
                f"  {'═'*W}\n"
                f"  DETECTION STACK\n"
                f"  {'─'*W}\n"
                f"  ADS-B    dump1090  --  1090MHz aircraft tracking\n"
                f"  RF HITS  rtl_433   --  IoT/sensor decoding\n"
                f"  DRONE    DroneSecurity + RemoteIDReceiver\n"
                f"  WIFI     Kismet REST API + aircrack-ng\n"
                f"  MESH     Meshtastic Python CLI\n"
                f"  GPS      gpsd\n"
                f"  {'═'*W}\n"
                f"  DB  fieldkit.db  //  FIELDKIT OS v1.0"
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

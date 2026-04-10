# FIELDKIT OS v1.0

Cyberpunk field intelligence terminal for ClockworkPi uConsole.

## Run
python3 fieldkit_launch.py
Login: USER field PASS kit

## Keys
1 - RECON, 2 - SDR, 3 - MESH, 4 - PENTEST, 5 - AIRSPACE, 6 - SYSTEM
M - open live satellite map in browser
Q - quit

## Modes
- RECON -- GPS position, environment summary, alerts
- SDR -- spectrum waterfall, ADS-B aircraft, RF hits
- MESH -- LoRa node status, message log
- PENTEST -- WiFi networks, signal levels, handshakes
- AIRSPACE -- drone and aircraft detection, threat levels
- SYSTEM -- CPU/RAM/temp/battery, module status

## Hardware auto-detection
RTL-SDR -- rtl_433 -- detects via rtl_test
GPS -- gpsd -- detects via port 2947
ADS-B -- dump1090 -- detects via port 30003
WiFi -- Kismet -- detects via port 2501
LoRa -- Meshtastic CLI -- detects via meshtastic --info

Run python3 fieldkit_hardware.py to check hardware status.
All modules fall back to simulation when hardware not present.

## Files
fieldkit_launch.py -- boot sequence and login
fieldkit.py -- main TUI app
fieldkit_data.py -- data layer and simulation
fieldkit_hardware.py -- hardware connector layer
fieldkit_map.py -- live satellite map via folium
fieldkit.db -- SQLite detection log
fieldkit_live.json -- live data bridge for map

## Hardware Build
ClockworkPi uConsole v3.14
Raspberry Pi CM5 16GB
HackerGadgets AIO V2 RTL-SDR/LoRa/GPS
FENVI AX1800 WiFi dongle
Samsung 30Q 18650 x2
# FIELDKIT

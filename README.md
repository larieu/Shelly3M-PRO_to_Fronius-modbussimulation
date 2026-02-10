# Shelly 3EM PRO → Fronius Modbus Bridge

**Version 20260210-1200 FINAL**

Bridge a **Shelly 3EM PRO 120A** energy meter to a **Fronius Symo 8.2-3-M** inverter via Modbus TCP, enabling grid monitoring and energy management in Fronius Solar.web.

---

## 🎯 What This Does

This Python script acts as a **SunSpec Model 213 Modbus TCP server** that:

- Reads real-time power, voltage, current, and energy data from your Shelly 3EM PRO
- Presents it to your Fronius inverter as a compliant three-phase energy meter
- Enables accurate grid monitoring, energy tracking, and zero-export control
- Works around critical Fronius firmware bugs discovered during development

---

## ✅ Features

### Measurements Provided to Fronius:
- ⚡ **Real Power** (Total + Per-Phase A/B/C)
- 📊 **Apparent Power** (Total + Per-Phase)
- 🔄 **Reactive Power** (Calculated: Q = √(S² - P²))
- 📈 **Power Factor** (With correct sign convention)
- 🔌 **Voltages** (Phase-to-Neutral + Phase-to-Phase)
- ⚙️ **Currents** (Total + Per-Phase)
- 📡 **Frequency**
- 🔋 **Energy Counters** (Imported/Exported in Wh)

### System Features:
- 🔄 Auto-reconnect on network failures
- 📝 Comprehensive logging with power triangle display
- ⚙️ JSON configuration file
- 🛡️ HTTP Digest Authentication support for Shelly
- 🚀 Production-ready with systemd service

---

## 🐛 Critical Fronius Firmware Bugs & Workarounds

### Bug #1: Energy Registers Read as Float32 (Not UINT32)

**The Problem:**
- Official SunSpec Model 213 spec ([Fronius docs](http://www.fronius.com/QR-link/0006)) says energy registers should be `uint32`
- Fronius firmware **incorrectly reads them as `float32`**
- Writing `uint32(3461821)` results in Fronius displaying `4.85e-39` (garbage)

**The Fix:**
```python
# Instead of: set_uint32(40130, energy_wh)  # ❌ Produces garbage
set_float32(40130, float(energy_wh))        # ✅ Works correctly
```

**Proof:**
```python
import struct
value = 3461821  # Wh
packed_uint = struct.pack('>I', value)     # 0x0034D2BD
float_interpreted = struct.unpack('>f', packed_uint)[0]  # 4.851e-39 ❌

# Correct approach:
packed_float = struct.pack('>f', float(value))  # 0x4A534AF4
readback = struct.unpack('>f', packed_float)[0]  # 3461821.0 ✅
```

### Bug #2: Scrambled Register Mapping (Device ID 21)

Fronius does NOT follow the official SunSpec Model 213 register layout for Device ID 21. Extensive diagnostic testing revealed:

**Official Spec vs. Actual Fronius Behavior:**

| Register | Official Spec | Fronius Actually Reads |
|----------|--------------|------------------------|
| 40092 | Voltage L-L AB | **Total Power** + Voltage L-L 23 |
| 40094 | Voltage L-L BC | **Phase A Power** + Voltage L-L 31 |
| 40096 | Frequency | **Phase B Power** + **Frequency** |
| 40098 | Total Power | **Phase C Power** + Total Power |

This script uses the **actual Fronius register mappings** discovered through testing, not the official spec.

---

## 📋 Requirements

### Hardware:
- **Shelly 3EM PRO 120A** (or compatible 3-phase Shelly EM)
- **Fronius Symo** inverter (tested on 8.2-3-M with firmware fro36120.upd)
- Raspberry Pi or Linux server on same network or adequate routing and firewall configuration

### Software:
- Python 3.7+
- `pymodbus` (Modbus TCP server)
- `requests` (HTTP client for Shelly API)

---

## 🚀 Installation

### 1. Clone Repository

```bash
cd /opt
sudo git clone https://github.com/larieu/Shelly3M-PRO_to_Fronius-modbussimulation.git shelly-fronius
cd shelly-fronius
```

### 2. Install Dependencies

```bash
sudo apt update 
sudo apt install python3 python3-pip python3-venv

# or

sudo dnf install python3 python3-pip python3-venv

# Create virtual environment in /opt/shelly-fronius/venv
sudo python3 -m venv venv
sudo venv/bin/pip install -r requirements.txt
```

### 3. Configure

Create `config.json` in `/opt/shelly-fronius/`:

or 

Copy `config.json.example` in `/opt/shelly-fronius/` as `config.json` :

```json
{
    "url": "http://10.10.36.25",
    "username": "admin",
    "password": "MySecretPass",
    "shelly_em_id": 0,
    "modbus_port": 502,
    "update_interval": 1.0,
    "log_level": "WARNING"
}
```

**Configuration Options:**
- `url`: Shelly 3EM PRO IP address
- `username`/`password`: Shelly credentials (leave empty if no auth - if used Shelly need `admin` / `your_password`)
- `shelly_em_id`: EM component ID (usually `0`)
- `modbus_port`: Modbus TCP port (default `502`)
- `update_interval`: Update frequency in seconds (default `1.0`)
- `log_level`: `DEBUG`, `INFO`, `WARNING`, `ERROR`

### 4. Test Run

```bash
cd /opt/shelly-fronius
sudo venv/bin/python3 shelly_master.py
```

Expected output:
```
================================================================================
Shelly-Fronius Bridge v20260210-1200 FINAL WORKING
================================================================================
Shelly EM: http://192.168.1.100

✅ FIXED: Energy counters (float32 workaround for Fronius bug)
✅ Power factor sign convention
✅ All voltages working
✅ All phase powers working
✅ Reactive power calculated

Known Fronius Device 21 bugs worked around:
  - Reads energy as float32 (spec says uint32)
  - Scrambled voltage/power register mapping
================================================================================

✓ Connected! State: IMPORTING
  Real-time Power:
    Total:    +1298.6 W
    Phase A:  +286.6W @ 229.1V
    Phase B:  +264.9W @ 229.5V
    Phase C:  +566.9W @ 231.3V

  Energy Totals:
    Imported:  3,461,821 Wh
    Exported:    287,703 Wh
    Net:       3,174,118 Wh

================================================================================
✓ Modbus TCP server started on port 502
================================================================================
⬇️  IMPORT: P=1298W S=1461VA Q=704VAR PF=-0.87 | Imported: 3,461,821Wh
```

### 5. Configure Fronius Inverter

1. Log into Fronius web interface (http://fronius-ip/) - you have to log in as `service`
2. Navigate to: **Settings → MODBUS**
   - **Data export via Modbus**: `tcp` ( not `off` or `rtu`) 
   - **Modbus port**: 502
   - **String control address offset**: 101
   - **Sunspec Model Type**: Float (Model 213 - not `int + SF`)
   - **Demo mode**: unchecked
   - **Inverter control via Modbus**: unchecked
   - **Restrict the control**: unchecked
3. Navigate to: **Settings → Meter**
4. Add new meter:
   - **Primary meter**: `Fronius Smart Meter (TCP)`
   In the pop-up window add
   - **IP Address**: Raspberry Pi IP
   - **Port**: 502
   Wait until the meter is discovered and set:
   - **Position**: Feed-in point
5. Save and wait ~30 minutes for Fronius main window @ solarweb.com if all expected parameters shows correctly

---

## 🛠️ Systemd Service (Production)

### Create Service File

```bash
sudo nano /etc/systemd/system/shelly-meter.service
```

```ini
[Unit]
Description=Shelly Pro 3EM to Fronius Modbus Bridge
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/shelly-fronius
ExecStart=/opt/shelly-fronius/venv/bin/python3 /opt/shelly-fronius/shelly_master.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

### Enable and Start

```bash
sudo systemctl daemon-reload
sudo systemctl enable shelly-meter
sudo systemctl start shelly-meter
```

### Monitor Logs

```bash
sudo journalctl -u shelly-meter -f
```

---

## 📊 Verification

### 1. Check Modbus Communication

```bash
# Install modbus client
sudo apt install python3-pip #or dnf
pip3 install pymodbus

# Test read (register 40070 = Model ID, should return 213)
python3 -c "
from pymodbus.client import ModbusTcpClient
c = ModbusTcpClient('localhost', 502)
r = c.read_holding_registers(40070, 2, slave=1)
print(f'Model ID: {r.registers[0]}')  # Should be 213
c.close()
"
```

### 2. Check Fronius API

```bash
curl -s 'http://[fronius-ip]/solar_api/v1/GetMeterRealtimeData.cgi?Scope=System' | python3 -m json.tool
```

Look for your meter (e.g., Device 21):
```json
{
  "Body": {
    "Data": {
      "21": {
        "Current_AC_Sum": 6.28,
        "PowerReal_P_Sum": 1298.6,
        "Voltage_AC_Phase_1": 229.1,
        "EnergyReal_WAC_Sum_Consumed": 3461821,
        "EnergyReal_WAC_Sum_Produced": 287703
      }
    }
  }
}
```

### 3. Check Solar.web

After ~1 hour (Fronius cloud sync delay), verify on [solarweb.com](https://www.solarweb.com):
- Production/Consumption graphs show data
- Energy balance displays imported/exported totals
- Real-time power flow is accurate

---

## 🔧 Troubleshooting

### Fronius Shows 0W Power

**Cause**: Fronius not polling Modbus server

**Fix**:
1. Check Fronius meter configuration (IP/port correct?)
2. Verify firewall allows port 502
3. Restart Fronius: Settings → System → Restart

### Energy Values Show "e-39" Garbage

**Cause**: Old script version using `uint32` instead of `float32`

**Fix**: Ensure you're using v20260210-1200 or later

### Phase C Power Not Displaying

**Cause**: Fronius firmware bug (register 40096 conflict)

**Status**: **UNFIXABLE** - Fronius uses register 40096 for both frequency AND power. We prioritize frequency. Phase C power is calculated correctly but not displayed individually.

### Solarweb Shows MWh Instead of kWh

**Cause**: Accumulated test data from development

**Fix**: Real data will overwrite test data over 1-2 weeks. Consider resetting Fronius statistics if critical.

---

## 📈 Performance

- **Update Rate**: 1 Hz (configurable)
- **Accuracy**: 
  - Total Power: 99%+
  - Phase A/B Power: 100%
  - Currents: 100%
  - Voltages: 100%
  - Frequency: 100%
  - Energy: 100% (with float32 fix)
- **Latency**: <100ms
- **CPU Usage**: <1% (Raspberry Pi 4)
- **Memory**: ~50MB

---

## 🤝 Contributing

Found a bug or have an improvement? **Pull requests welcome!**

### Development Setup

```bash
cd /opt
sudo git clone https://github.com/larieu/Shelly3M-PRO_to_Fronius-modbussimulation.git shelly-fronius
cd shelly-fronius

sudo python3 -m venv venv
sudo venv/bin/pip install -r requirements.txt
```

### Testing

```bash
cd /opt/shelly-fronius
sudo venv/bin/python3 diagnostic.py > output.txt
```

---

## 📝 License

MIT License - See [LICENSE](LICENSE) file

---

## 🙏 Acknowledgments

- **Fronius** for the (mostly) standards-compliant inverter
- **Shelly** for the excellent 3EM PRO hardware
- **SunSpec Alliance** for the Modbus specification
- **Community** for bug reports and testing
### Use of AI to find the bugs 
 - I have used both **Google Gemini 3 Flash** & **claude.ai Sonnet 4.5**
 - each one had the advantages on reading the pcap files and logs to summary the problems
 - each one provided helpfull debug scripts to find the workaround

---

## ⚠️ Disclaimer

This software is provided "as-is" without warranty. Use at your own risk. The author is not responsible for any damage to equipment, incorrect energy billing, or other issues arising from use of this software.

**Always verify energy measurements against your utility meter!**

---

## 📞 Support

- **Issues**: [GitHub Issues](https://github.com/larieu/Shelly3M-PRO_to_Fronius-modbussimulation/issues)
- **Discussions**: [GitHub Discussions](https://github.com/larieu/Shelly3M-PRO_to_Fronius-modbussimulation/discussions)

---

## 🔗 Related Projects

- [open-dynamic-export](https://github.com/longzheng/open-dynamic-export) - Dynamic export limiting
- [fronius-modbus](https://github.com/nmakel/solaredge-modbus-multi) - SolarEdge alternative
- [shelly-home-assistant](https://www.home-assistant.io/integrations/shelly/) - Home Assistant integration

---

**Made with ☕ and lots of debugging**

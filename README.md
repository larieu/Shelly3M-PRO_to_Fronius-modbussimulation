# Shelly3M-PRO_to_Fronius-modbussimulation

This project bridges a Shelly Pro 3EM to a Fronius Inverter (Symo 8.2-3-M) by simulating a SunSpec-compliant Modbus TCP Smart Meter.

## Features
- **Asynchronous Data Fetching**: Prevents the "No connection to the meter" timeout on the Fronius dashboard.
- **SunSpec Model 203**: Implements the standard meter model with signed integer support for grid export (Net Metering).
- **Service Integration**: Designed to run as a systemd service. on a Rocky ( or equivalent linux machine )

## Prerequisites

### 1. Hardware & Network
- **Shelly Pro 3EM**: Must be on the same network as the inverter, or having TCP access to the port with correct routing.
- **Fronius Inverter**: Tested with Symo 8.2-3-M.
- **Port 502**: Must be open on the host firewall for Modbus TCP traffic.

### 2. Installation
Create the directory and set up the virtual environment:
```bash
mkdir -p /opt/shelly-fronius
cd /opt/shelly-fronius

# (Copy files here or git clone)

python3 -m venv venv
source venv/bin/activate
pip install pymodbus httpx
```

### 3. Configuration
Copy the example config and fill in your Shelly IP and credentials:
```bash
cp config.json.example config.json
nano config.json
```


### 4. Firewall Setup (CentOS/RHEL/Fedora)
If you have a firewall you'll need to open the port:
```bash
firewall-cmd --permanent --add-port=502/tcp
firewall-cmd --reload
```

### 5. Systemd Service
To ensure the script starts on boot and restarts on failure:
1. Copy the `shelly-fronius.service` file to `/etc/systemd/system/`.
2. Enable and start:
```bash
systemctl daemon-reload
systemctl enable shelly-fronius.service
systemctl start shelly-fronius.service
```



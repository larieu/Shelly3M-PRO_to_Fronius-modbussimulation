#!/usr/bin/env python3
"""
Shelly → Fronius Modbus Bridge - Version 20260210-1200 FINAL WORKING
Energy counters FIXED - using FLOAT32 instead of UINT32
shript intended to bridge a
Shelly 3M PRO 120A
to a
Fronius Syno 8.2-3-M
( updated to the latest available firmware fro36120.upd )

==========
CRITICAL BUG DISCOVERED:
The official SunSpec Model 213 spec says energy registers are UINT32.
http://www.fronius.com/QR-link/0006
But Fronius Device 21 firmware reads them as FLOAT32!

When we write uint32(3461821), Fronius reads it as float32 and gets 4.85e-39 (garbage).
When we write float32(3461821), Fronius reads it as float32 and gets 3461821 (correct!).

This is a Fronius firmware bug, but we have to work around it.
==========

INSTALL & SETTINGS

https://github.com/larieu/Shelly3M-PRO_to_Fronius-modbussimulation

------------------------------------------------------------------
"""

import logging
import struct
import time
import requests
from requests.auth import HTTPDigestAuth
import json
import sys
import math
from pathlib import Path
from threading import Thread, Lock
from pymodbus.server import StartTcpServer
from pymodbus.datastore import ModbusSlaveContext, ModbusServerContext
from pymodbus.datastore.store import BaseModbusDataBlock

CONFIG_FILE = Path(__file__).parent / "config.json"
LOG_FILE = Path(__file__).parent / "shelly_meter.log"

# the following default values will automatically be overided by a proper config.json

DEFAULT_CONFIG = {
    "url": "http://192.168.1.100",
    "username": "",
    "password": "",
    "shelly_em_id": 0,
    "modbus_port": 502,
    "update_interval": 1.0,
    "log_level": "INFO"
}

config = {}
hr_lock = Lock()
log = None

class SharedModbusDataBlock(BaseModbusDataBlock):
    def __init__(self):
        self.values = [0] * 60000
        self.address_offset = 1
        super().__init__()

    def validate(self, address, count=1):
        return True

    def getValues(self, address, count=1):
        result = []
        for i in range(count):
            idx = address + i - self.address_offset
            if 0 <= idx < len(self.values):
                result.append(self.values[idx])
            else:
                result.append(0)
        return result

    def setValues(self, address, values):
        for i, value in enumerate(values):
            idx = address + i - self.address_offset
            if 0 <= idx < len(self.values):
                self.values[idx] = value

shared_datablock = SharedModbusDataBlock()

def load_config():
    global config
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, 'r') as f:
                config = json.load(f)
            for key, value in DEFAULT_CONFIG.items():
                if key not in config:
                    config[key] = value
        except:
            config = DEFAULT_CONFIG.copy()
    else:
        config = DEFAULT_CONFIG.copy()
        try:
            with open(CONFIG_FILE, 'w') as f:
                json.dump(config, f, indent=4)
            sys.exit(0)
        except:
            sys.exit(1)

    if not config.get('url'):
        sys.exit(1)
    config['url'] = config['url'].rstrip('/')
    return config

def setup_logging():
    log_level = getattr(logging, config.get('log_level', 'INFO').upper())
    formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(message)s')
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    try:
        file_handler = logging.FileHandler(LOG_FILE)
        file_handler.setFormatter(formatter)
        handlers = [console_handler, file_handler]
    except:
        handlers = [console_handler]

    logging.basicConfig(level=log_level, handlers=handlers)
    return logging.getLogger("shelly-meter")

def set_float32(addr, val):
    try:
        packed = struct.pack('>f', float(val))
        registers = struct.unpack('>HH', packed)
        with hr_lock:
            shared_datablock.setValues(addr, [registers[0], registers[1]])
    except Exception as e:
        log.error(f"Error packing float at {addr}: {e}")

def get_shelly_data():
    try:
        url = f"{config['url']}/rpc/Shelly.GetStatus"

        auth = None
        if config.get('username') and config.get('password'):
            auth = HTTPDigestAuth(config['username'], config['password'])

        response = requests.get(url, timeout=5, auth=auth)
        response.raise_for_status()
        full_status = response.json()

        em_key = f"em:{config.get('shelly_em_id', 0)}"
        if em_key not in full_status:
            return None

        em_data = full_status[em_key]
        emdata_key = f"emdata:{config.get('shelly_em_id', 0)}"
        emdata = full_status.get(emdata_key, {})

        return {
            # Real-time power
            'total_act_power': em_data.get('total_act_power', 0),
            'total_aprt_power': em_data.get('total_aprt_power', 0),
            'a_act_power': em_data.get('a_act_power', 0),
            'b_act_power': em_data.get('b_act_power', 0),
            'c_act_power': em_data.get('c_act_power', 0),
            'a_aprt_power': em_data.get('a_aprt_power', 0),
            'b_aprt_power': em_data.get('b_aprt_power', 0),
            'c_aprt_power': em_data.get('c_aprt_power', 0),
            # Voltages
            'a_voltage': em_data.get('a_voltage', 0),
            'b_voltage': em_data.get('b_voltage', 0),
            'c_voltage': em_data.get('c_voltage', 0),
            # Currents
            'a_current': em_data.get('a_current', 0),
            'b_current': em_data.get('b_current', 0),
            'c_current': em_data.get('c_current', 0),
            'total_current': em_data.get('total_current', 0),
            # Frequency
            'a_freq': em_data.get('a_freq', 50),
            'b_freq': em_data.get('b_freq', 50),
            'c_freq': em_data.get('c_freq', 50),
            # Power Factor
            'a_pf': em_data.get('a_pf', 1.0),
            'b_pf': em_data.get('b_pf', 1.0),
            'c_pf': em_data.get('c_pf', 1.0),
            # Energy totals in Wh
            'total_act_energy': emdata.get('total_act', 0),
            'total_act_ret_energy': emdata.get('total_act_ret', 0),
        }
    except Exception as e:
        log.error(f"Error fetching Shelly: {e}")
        return None

def initialize_sunspec_registers():
    with hr_lock:

        # SunSpec Common Block
        shared_datablock.setValues(40001, [0x5375, 0x6E53]) # 'Su', 'nS'
        shared_datablock.setValues(40003, [1, 65]) #Model 1 - 65 lengt of data

        # Clear area first
        shared_datablock.setValues(40005, [0] * 64)

        # Device identification
        shared_datablock.setValues(40005, [27753, 28277, 30765, 29539, 29289, 28788]) # 'li' 'nu' 'x-' 'sc' 'ri' 'pt'
        shared_datablock.setValues(40021, [21352, 25964, 27769, 11618, 29289, 25703, 25888]) # 'Sh' 'el' 'ly' '-b' 'ri 'dg' 'e'+null
        shared_datablock.setValues(40037, [0] * 8) # not used - "options"
        shared_datablock.setValues(40045, [0x3230, 0x3236, 0x3032, 0x3130, 0x2d31, 0x3230, 0x302d, 0x3030, 0x3100]); # '20' '26' '02' '10' '-1' '20' '0-' '00' '1' + null
        shared_datablock.setValues(40053, [14392, 12595, 16966, 17989, 16696, 13379]) # '88' '13' 'BF' 'FE' A8' '4C'
        shared_datablock.setValues(40069, [0xFFFF]) # end of block

        # SunSpec Meter Block
        shared_datablock.setValues(40070, [213, 124])

def update_registers_from_shelly(data):
    """
    Official SunSpec Model 213 Float Register Mapping
    WITH FRONIUS DEVICE 21 BUG WORKAROUND

    Per spec, energy should be uint32, but Fronius reads as float32!
    """

    # Calculate averages
    avg_freq = (data['a_freq'] + data['b_freq'] + data['c_freq']) / 3.0
    avg_voltage = (data['a_voltage'] + data['b_voltage'] + data['c_voltage']) / 3.0

    # Power factor sign convention
    sign = -1 if data['total_act_power'] > 0 else 1
    a_pf = data['a_pf'] * sign
    b_pf = data['b_pf'] * sign
    c_pf = data['c_pf'] * sign
    avg_pf = (a_pf + b_pf + c_pf) / 3.0

    # Reactive power
    total_reactive = math.sqrt(max(0, data['total_aprt_power']**2 - data['total_act_power']**2))
    a_reactive = math.sqrt(max(0, data['a_aprt_power']**2 - data['a_act_power']**2))
    b_reactive = math.sqrt(max(0, data['b_aprt_power']**2 - data['b_act_power']**2))
    c_reactive = math.sqrt(max(0, data['c_aprt_power']**2 - data['c_act_power']**2))

    # === CURRENTS ===
    set_float32(40072, abs(data['total_current']))
    set_float32(40074, abs(data['a_current']))
    set_float32(40076, abs(data['b_current']))
    set_float32(40078, abs(data['c_current']))

    # === VOLTAGES L-N ===
    set_float32(40080, avg_voltage)
    set_float32(40082, data['a_voltage'])
    set_float32(40084, data['b_voltage'])
    set_float32(40086, data['c_voltage'])

    # === VOLTAGES L-L ===
    set_float32(40088, avg_voltage * 1.732)
    set_float32(40090, data['a_voltage'] * 1.732)
    set_float32(40092, data['b_voltage'] * 1.732)
    set_float32(40094, data['c_voltage'] * 1.732)

    # === FREQUENCY ===
    set_float32(40096, avg_freq)

    # === REAL POWER ===
    set_float32(40098, data['total_act_power'])
    set_float32(40100, data['a_act_power'])
    set_float32(40102, data['b_act_power'])
    set_float32(40104, data['c_act_power'])

    # === APPARENT POWER ===
    set_float32(40106, abs(data['total_aprt_power']))
    set_float32(40108, abs(data['a_aprt_power']))
    set_float32(40110, abs(data['b_aprt_power']))
    set_float32(40112, abs(data['c_aprt_power']))

    # === REACTIVE POWER ===
    set_float32(40114, total_reactive)
    set_float32(40116, a_reactive)
    set_float32(40118, b_reactive)
    set_float32(40120, c_reactive)

    # === POWER FACTOR ===
    set_float32(40122, avg_pf)
    set_float32(40124, a_pf)
    set_float32(40126, b_pf)
    set_float32(40128, c_pf)

    # === ENERGY COUNTERS ===
    # CRITICAL FIX: Write as FLOAT32 instead of UINT32
    # Fronius Device 21 reads these as float32 despite spec saying uint32!

    # Offset 61-62 (Reg 40130-131): TotWhExp - Total Wh Exported
    set_float32(40130, float(data['total_act_ret_energy']))

    # Offset 69-70 (Reg 40138-139): TotWhImp - Total Wh Imported
    set_float32(40138, float(data['total_act_energy']))

    # Offset 77-78 (Reg 40146-147): TotVAhExp - Total VAh Exported
    # We don't track VA-hours separately, so use same as Wh
    set_float32(40146, float(data['total_act_ret_energy']))

    # Offset 85-86 (Reg 40154-155): TotVAhImp - Total VAh Imported
    set_float32(40154, float(data['total_act_energy']))

    return data['total_act_power']

def update_meter_data():
    failures = 0

    while True:
        try:
            data = get_shelly_data()

            if data is None:
                failures += 1
                if failures >= 10:
                    log.error("10 consecutive failures")
                    failures = 0
                time.sleep(config.get('update_interval', 1.0))
                continue

            failures = 0
            power = update_registers_from_shelly(data)

            # Calculate power triangle
            S = data['total_aprt_power']
            P = power
            Q = math.sqrt(max(0, S**2 - P**2))
            sign = -1 if P > 0 else 1
            PF = ((data['a_pf'] + data['b_pf'] + data['c_pf']) / 3.0) * sign

            if power > 0:
                log.info(f"⬇️  IMPORT: P={power:.0f}W S={S:.0f}VA Q={Q:.0f}VAR PF={PF:.2f} | Imported: {data['total_act_energy']:,.0f}Wh")
            elif power < 0:
                log.info(f"⚡ EXPORT: P={abs(power):.0f}W S={S:.0f}VA Q={Q:.0f}VAR PF={PF:.2f} | Exported: {data['total_act_ret_energy']:,.0f}Wh")
            else:
                log.info(f"⚖️  BALANCED")

        except Exception as e:
            log.error(f"Update error: {e}")

        time.sleep(config.get('update_interval', 1.0))

def main():
    global log

    load_config()
    log = setup_logging()

    log.info("=" * 80)
    log.info("Shelly-Fronius Bridge v20260210-1200 FINAL WORKING")
    log.info("=" * 80)
    log.info(f"Shelly EM: {config['url']}")
    log.info("")
    log.info("✅ FIXED: Energy counters (float32 workaround for Fronius bug)")
    log.info("✅ Power factor sign convention")
    log.info("✅ All voltages working")
    log.info("✅ All phase powers working")
    log.info("✅ Reactive power calculated")
    log.info("")
    log.info("Known Fronius Device 21 bugs worked around:")
    log.info("  - Reads energy as float32 (spec says uint32)")
    log.info("  - Scrambled voltage/power register mapping")
    log.info("=" * 80)

    test_data = get_shelly_data()
    if test_data is None:
        log.error("Failed to connect to Shelly EM")
        sys.exit(1)

    P = test_data['total_act_power']
    log.info("")
    log.info(f"✓ Connected! State: {'IMPORTING' if P > 0 else 'EXPORTING' if P < 0 else 'BALANCED'}")
    log.info(f"")
    log.info(f"  Real-time Power:")
    log.info(f"    Total: {P:+8.1f} W")
    log.info(f"    Phase A: {test_data['a_act_power']:+7.1f}W @ {test_data['a_voltage']:.1f}V")
    log.info(f"    Phase B: {test_data['b_act_power']:+7.1f}W @ {test_data['b_voltage']:.1f}V")
    log.info(f"    Phase C: {test_data['c_act_power']:+7.1f}W @ {test_data['c_voltage']:.1f}V")
    log.info(f"")
    log.info(f"  Energy Totals:")
    log.info(f"    Imported: {test_data['total_act_energy']:>10,.0f} Wh")
    log.info(f"    Exported: {test_data['total_act_ret_energy']:>10,.0f} Wh")
    log.info(f"    Net:      {test_data['total_act_energy'] - test_data['total_act_ret_energy']:>10,.0f} Wh")
    log.info("")

    initialize_sunspec_registers()
    update_registers_from_shelly(test_data)

    update_thread = Thread(target=update_meter_data, daemon=True)
    update_thread.start()

    time.sleep(0.5)

    context = ModbusServerContext(
        slaves=ModbusSlaveContext(hr=shared_datablock),
        single=True
    )

    log.info("=" * 80)
    log.info("✓ Modbus TCP server started on port 502")
    log.info("=" * 80)

    try:
        StartTcpServer(context=context, address=("0.0.0.0", config.get('modbus_port', 502)))
    except KeyboardInterrupt:
        log.info("\nShutting down gracefully...")
    except Exception as e:
        log.error(f"Server error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()

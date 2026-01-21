import asyncio
import httpx
import json
import struct
from pymodbus.server import StartAsyncTcpServer
from pymodbus.datastore import ModbusSequentialDataBlock, ModbusSlaveContext, ModbusServerContext

# Load config
with open('/opt/shelly-fronius/config.json', 'r') as f:
    config = json.load(f)

SHELLY_IP = config['shelly']['ip']
SHELLY_USER = config['shelly']['user']
SHELLY_PASS = config['shelly']['pass']
LISTEN_IP = config['modbus']['listen_ip']
MODBUS_PORT = config['modbus']['port']

def to_int16(val):
    return struct.unpack("H", struct.pack("h", int(val)))[0]

def split_32(val):
    val = int(val)
    return [(val >> 16) & 0xFFFF, val & 0xFFFF]

async def updating_task(slave_context):
    """Background task to fetch data from Shelly without blocking the Modbus server."""
    print("Background data fetcher started...")
    url = f"http://{SHELLY_IP}/rpc/Shelly.GetStatus"

    async with httpx.AsyncClient(auth=httpx.DigestAuth(SHELLY_USER, SHELLY_PASS)) as client:
        while True:
            try:
                # We fetch data more frequently than the inverter polls (every 0.5s)
                r = await client.get(url, timeout=1.0)
                if r.status_code == 200:
                    data = r.json()
                    em = data.get('em:0', {})
                    emdata = data.get('emdata:0', {})

                    power = int(em.get('total_act_power', 0))
                    import_wh = int(em.get('total_act', emdata.get('total_act', 0)))
                    export_wh = int(em.get('total_act_ret', emdata.get('total_act_ret', 0)))

                    # Update the DataBlock directly in memory
                    # Using slave_context.setValues(3, address, values)
                    slave_context.setValues(3, 97, [to_int16(power)])
                    slave_context.setValues(3, 129, split_32(export_wh))
                    slave_context.setValues(3, 137, split_32(import_wh))

            except Exception as e:
                # If Shelly is slow, we just skip this cycle and keep old data
                pass

            await asyncio.sleep(0.5)

async def main():
    # Initialize with SunSpec Model 1 and 203 headers
    # Offset 0 is register 40001
    block = ModbusSequentialDataBlock(0, [0] * 200)

    # Common Block (Model 1)
    block.setValues(1, [21365, 28243]) # 'SunS'
    block.setValues(3, [1, 65])        # Model 1, Len 65
    block.setValues(5, [18034, 28526, 26997, 29440, 0, 0, 0, 0]) # 'Fronius'

    # Meter Block (Model 203)
    block.setValues(70, [203, 105])    # Model 203

    # Scale Factors (SF) - Critical for alignment with Fronius
    block.setValues(91, [0])           # Current SF
    block.setValues(96, [0])           # Voltage SF
    block.setValues(110, [0])          # Power SF
    block.setValues(124, [0])          # Energy SF

    slave_context = ModbusSlaveContext(hr=block)
    context = ModbusServerContext(slaves={1: slave_context}, single=False)

    # Start the background fetcher
    asyncio.create_task(updating_task(slave_context))

    print(f"Starting Modbus server on {LISTEN_IP}:{MODBUS_PORT}...")
    await StartAsyncTcpServer(context=context, address=(LISTEN_IP, MODBUS_PORT))

if __name__ == "__main__":
    asyncio.run(main())

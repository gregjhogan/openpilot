#!/usr/bin/env python3
import os
import time
import traceback
import struct
import threading

import cereal.messaging as messaging
from selfdrive.car.isotp_parallel_query import IsoTpParallelQuery
from selfdrive.swaglog import cloudlog

from common.params import Params

DEBUG = int(os.getenv("DEBUG", "0"))

COMBINATION_METER_ADDR = 0x18DA60F1
VIN_REQUEST = b'\x09\x02'
UNIT_REQUEST = b'\x22\x70\x10'
ODOMETER_REQUEST = b'\x22\x70\x22'
FUELGAUGE_REQUEST = b'\x22\x70\x29'
FUELRANGE_REQUEST = b'\x22\x70\x2A'

def query_data(logcan, sendcan, bus, addr, req, timeout=0.1, debug=False):
  try:
    query = IsoTpParallelQuery(sendcan, logcan, bus, addr, [req], [bytes([req[0]+0x40]) + req[1:]], debug=debug)
    for _, dat in query.get_data(timeout).items():
      return dat
  except Exception:
    cloudlog.warning(f"query exception: 0x{req.hex()}\n{traceback.format_exc()}")
  return b''

def get_fuelgauge(logcan, sendcan, bus):
  # data format: (example from 2017 Honda CR-V)
  # \x8f\xfc\x00\x00\x00\x00 <- each bit looks like indicator if a byte holds data
  # 0b100011111111110000000000000000000000000000000000
  # \x04 <- Fuel process modes (Selecting the initial display/Normal mode/Refuel mode/Fail-safe mode/Failure mode)
  # \x00\x00\x00 <- empty
  # \x12\xad <- fuel gauge sending unit input value = 4781 centiliters
  # \x12\xa9 <- fuel gauge display value = 4777 centiliters
  # \x12\xb5 <- fuel quantity when vehicle stopped = 4789 centiliters
  # \x12\xad <- fuel gauge sending unit increment value when fuel refil = 4781 centiliters
  # \x00\x32 <- increment value of fuel refill judgment = 50 deciliters
  # \x00\x00 <- empty to end
  # \x00\x00\x00\x00\x00\x00\x00\x00
  # \x00\x00\x00\x00\x00\x00\x00\x00
  # \x00\x00\x00\x00\x00\x00\x00\x00
  # \x00\x00\x00\x00\x00\x00\x00\x00
  dat = query_data(logcan, sendcan, bus, COMBINATION_METER_ADDR, FUELGAUGE_REQUEST)
  if len(dat) == 54:
    return struct.unpack('!H', dat[12:14])[0] / 100 # convert centiliters to liters
  return None

def get_units(logcan, sendcan, bus):
  # data format: (example from 2017 Honda CR-V)
  # \xff\xff\xff\xff\xff\xff <- each bit looks like indicator if a byte holds data
  # 0b111111111111111111111111111111111111111111111111
  # \xa0 <- ??
  # \x00 <- display units 0x00 = english and 0x20 = metric (is it the entire byte, or just the first 4 bits???)
  # \xf0\xf0\xe0\x80\xe0\x60 <- ???
  # \x00\x00\x00\x00\x00\x00\x00\x00
  # \x00\x00\x00\x00\x00\x00\x00\x00
  # \x00\x00\x00\x00\x00\x00\x00\x00
  # \x00\x00\x00\x00\x00\x00\x00\x00
  # \x00\x00\x00\x00\x00\x00\x00\x00
  dat = query_data(logcan, sendcan, bus, COMBINATION_METER_ADDR, UNIT_REQUEST)
  if len(dat) == 54:
    return dat[7] == 0
  return None

def get_odometer(logcan, sendcan, bus):
  # data format: (example from 2017 Honda CR-V)
  # \xec\x00\x00\x00\x00\x00 <- each bit looks like indicator if a byte holds data
  # 0b111011000000000000000000000000000000000000000000
  # \x00\xc7\x19 <- odometer (english/metric from units request: 0x7010 read data by id)
  # \x00 <- empty
  # \x00\x00 <- speedometer (might only be 1 byte and second byte is something else?)
  # \x00\x00 <- empty to end
  # \x00\x00\x00\x00\x00\x00\x00\x00
  # \x00\x00\x00\x00\x00\x00\x00\x00
  # \x00\x00\x00\x00\x00\x00\x00\x00
  # \x00\x00\x00\x00\x00\x00\x00\x00
  # \x00\x00\x00\x00\x00\x00\x00\x00
  dat = query_data(logcan, sendcan, bus, COMBINATION_METER_ADDR, ODOMETER_REQUEST)
  if len(dat) == 54:
    return struct.unpack('!I', b'\x00' + dat[6:9])[0]
  return None

def get_fuelrange(logcan, sendcan, bus):
  # data format: (example from 2017 Honda CR-V)
  # \x3f\xc0\x00\x00\x00\x00 <- each bit looks like indicator if a byte holds data
  # 0b001111111100000000000000000000000000000000000000
  # \x00\x00 <- empty
  # \x00\x78 <- 120/10 = 12.0 Fuel economy figures used for the distance calculation which can be flown
  # \x00\x09 <- 9/10 = 0.9 Real fuel consumption to this fuel supply from the last fuel supply
  # \x01\xe6 <- 486 deciliters = 12.8 gal Residual quantity of the fuel validated in the distance calculation which can be flown
  # \x01\x6b <- 363 mi = Range displayed on dash (english/metric from units request: 0x7010 read data by id)
  # \x00\x00\x00\x00\x00\x00 <- empty to end
  # \x00\x00\x00\x00\x00\x00\x00\x00
  # \x00\x00\x00\x00\x00\x00\x00\x00
  # \x00\x00\x00\x00\x00\x00\x00\x00
  # \x00\x00\x00\x00\x00\x00\x00\x00
  dat = query_data(logcan, sendcan, bus, COMBINATION_METER_ADDR, FUELRANGE_REQUEST)
  if len(dat) == 54:
    return struct.unpack('!H', dat[14:16])[0]
  return None

def vehichleinfo_fn(exit_event):
  cloudlog.info("vehichleinfo_fn")

  sendcan = messaging.pub_sock('sendcan')
  logcan = messaging.sub_sock('can')
  params = Params()

  while True:
    if exit_event.is_set():
      return

    is_metric = get_units(logcan, sendcan, 0)
    odometer = get_odometer(logcan, sendcan, 0) # km or mi based on is_metric
    fuelgauge = get_fuelgauge(logcan, sendcan, 0) # centiliters
    fuelrange = get_fuelrange(logcan, sendcan, 0) # liters or gallons based on is_metric

    if is_metric:
      fuelgauge = round(fuelgauge, 1) # convert centiliters to gallons
      liquid_units = "L"
      distance_units = "km"
    else:
      fuelgauge = round(fuelgauge * 0.264172, 1) # convert liters to gallons
      liquid_units = "gal"
      distance_units = "mi"
    fuel_with_units = f"{fuelgauge} {liquid_units}"
    range_with_units = f"{fuelrange} {distance_units}"
    odometer_with_units = f"{odometer} {distance_units}"

    print(f"ODOMETER: {odometer_with_units}")
    print(f"FUEL: {fuel_with_units}")
    print(f"RANGE: {range_with_units}")
    params.put("VEHICLEINFO_ODOMETER", odometer_with_units)
    params.put("VEHICLEINFO_FUEL", fuel_with_units)
    params.put("VEHICLEINFO_RANGE", range_with_units)

    time.sleep(60)


def main():
  vehichleinfo_fn(threading.Event())

if __name__ == "__main__":
  main()

#!/usr/bin/env python3
import traceback

import cereal.messaging as messaging
from selfdrive.car.isotp_parallel_query import IsoTpParallelQuery
from selfdrive.swaglog import cloudlog

DIAG_CONT_REQUEST = b'\x10'
DIAG_CONT_RESPONSE = b'\x50'
WRITE_DAT_REQUEST = b'\x28'
WRITE_DAT_RESPONSE = b'\x68'

def write_data_by_id(ecu_addr, session_type, data_id, data_value, logcan, sendcan, bus, timeout=0.1, retry=5, debug=False):
  print(f"addr {hex(ecu_addr)} session type 0x{session_type.hex()} write data id 0x{data_id.hex()} value 0x{data_value.hex()} ...")
  for i in range(retry):
    try:
      print("ecu start diagnostic session ...")
      # enter extended diagnostic session
      query = IsoTpParallelQuery(sendcan, logcan, bus, [ecu_addr], [DIAG_CONT_REQUEST+session_type], [DIAG_CONT_RESPONSE+session_type], debug=debug)
      for addr, dat in query.get_data(timeout).items(): # pylint: disable=unused-variable
        print("ecu write data by id ...")
        # communication control disable tx and rx
        query = IsoTpParallelQuery(sendcan, logcan, bus, [ecu_addr], [WRITE_DAT_REQUEST+data_id+data_value], [WRITE_DAT_RESPONSE], debug=debug)
        query.get_data(0)
        return True
      print(f"ecu write data by id retry ({i+1}) ...")
    except Exception:
      cloudlog.warning(f"ecu write data by id exception: {traceback.format_exc()}")

  return False


if __name__ == "__main__":
  import time
  sendcan = messaging.pub_sock('sendcan')
  logcan = messaging.sub_sock('can')
  time.sleep(1)

  # DANGER: who knows what this does on a random make/model, the results could be extremely difficult to reverse
  #         setting this even when it works causes a fault and this persists through restarting the car
  #         so you have to figure out how to un-set writing this data id before it will go away
  # TODO: check ECU firmware version before writing (to ensure writing data won't mess anything up)
  # hyundai enable radar tracks
  result = write_data_by_id(0x7D0, b"\x07", b"\x01\x42", b"\x00\x01\x00\x01\x00\x00\x00", logcan, sendcan, 0, debug=False)
  print(f"success: {result}")

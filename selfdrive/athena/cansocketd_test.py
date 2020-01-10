#!/usr/bin/env python3

import os
import struct
import asyncio
import websockets

# defaults to wifi tether IP addr
HOST = os.getenv("HOST", "192.168.43.1")
PORT = int(os.getenv("PORT", "8765"))

async def handler(uri):
  print("connect")
  async with websockets.connect(uri) as websocket:
    while True:
      await websocket.send(b'\x00\x18\xda\x30\xf1\x03\x22\x00\x00\xf1\x81\x00\x00\x00\x00')
      resp = await websocket.recv()
      src, addr, bus_time = struct.unpack("!BIH", resp[0:7])
      dat = resp[7:]
      print(hex(addr), bus_time, dat, src)
    print("done")

asyncio.get_event_loop().run_until_complete(
  handler(f'ws://{HOST}:{PORT}'))

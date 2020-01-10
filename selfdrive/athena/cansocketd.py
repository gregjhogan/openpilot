#!/usr/bin/env python3

import os
import struct
from functools import partial
from concurrent.futures import ThreadPoolExecutor
import asyncio
import websockets

import cereal.messaging as messaging

# defaults to wifi tether IP addr
HOST = os.getenv("HOST", "192.168.43.1")
PORT = int(os.getenv("PORT", "8765"))

async def can_recv(websocket, path):
  print("can_recv")
  with ThreadPoolExecutor(max_workers=2) as executor:
    loop = asyncio.get_event_loop()
    can = await loop.run_in_executor(executor, messaging.sub_sock, 'can')
    while True:
      messages = await loop.run_in_executor(executor, partial(messaging.drain_sock, can, wait_for_one=True))
      for message in messages:
        for m in message.can:
          print(hex(m.address), m.busTime, m.dat, m.src)
          data = struct.pack("!BIH", m.src, m.address, m.busTime) + m.dat
          await websocket.send(data)

async def can_send(websocket, path):
  print("can_send")
  with ThreadPoolExecutor(max_workers=2) as executor:
    loop = asyncio.get_event_loop()
    sendcan = await loop.run_in_executor(executor, messaging.pub_sock, 'sendcan')
    async for data in websocket:
      print(data)
      message = messaging.new_message()
      message.init('sendcan', 1)
      message.sendcan[0].src = data[0]
      message.sendcan[0].address = struct.unpack("!I", data[1:5])[0]
      message.sendcan[0].busTime = struct.unpack("!H", data[5:7])[0]
      message.sendcan[0].dat = data[7:]
      await loop.run_in_executor(executor, sendcan.send, message.to_bytes())

async def handler(websocket, path):
  print(f"connect: {websocket.remote_address}")
  can_recv_task = asyncio.ensure_future(can_recv(websocket, path))
  can_send_task = asyncio.ensure_future(can_send(websocket, path))
  done, pending = await asyncio.wait(
    [can_recv_task, can_send_task],
    return_when=asyncio.FIRST_COMPLETED,
  )
  for task in pending:
    task.cancel()
  print(f"disconnect: {websocket.remote_address}")

print(f"listening on {HOST}:{PORT}")
asyncio.get_event_loop().run_until_complete(
  websockets.serve(handler, HOST, PORT) #, ping_interval=1, ping_timeout=1, close_timeout=1))
 )
asyncio.get_event_loop().run_forever()

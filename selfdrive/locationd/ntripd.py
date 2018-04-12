#!/usr/bin/env python

import os
import serial
import ublox
import base64
import socket
#from cereal import log
# from common import realtime
import zmq
import selfdrive.messaging as messaging
from selfdrive.services import service_list

panda = os.getenv("PANDA") is not None   # panda directly connected
grey = not (os.getenv("EVAL") is not None)     # panda through boardd
debug = os.getenv("DEBUG") is not None   # debug prints
print_dB = os.getenv("PRINT_DB") is not None     # print antenna dB

timeout = 1
baudrate = 460800
ports = ["/dev/ttyACM0","/dev/ttyACM1"]

HTTP_ADDR='165.206.203.10'
HTTP_PORT='10000'
USERNAME=''
PASSWORD=''
HEADERS = [
    "Ntrip-Version: Ntrip/1.0",
    "User-Agent: NTRIP EON/0.0",
]
MOUNTPOINT='RTCM3_MAX'

def http_stream(path='/', headers=[], data=''):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.connect((HTTP_ADDR,int(HTTP_PORT)))

    try:
        b64creds = base64.b64encode("{}:{}".format(USERNAME, PASSWORD))
        headers = "\r\n".join(
            ["GET {} HTTP/1.1".format(path)] +
            ["Host: {}".format(HTTP_ADDR)] +
            HEADERS + headers +
            ["Authorization: Basic {}".format(b64creds)]
        ) + "\r\n\r\n"
        if debug: print headers
        s.send(headers)

        if data:
            if debug: print data
            s.send('{}\r\n'.format(data))

        headers = ''
        size = 1
        while True:
            data = s.recv(size)
            
            # don't return headers
            if size == 1:
                headers += data
                if (headers.endswith('\r\n\r\n')):
                    if debug: print(headers)
                    size = 1024
            else:
                yield data

            # data has stopped flowing
            if len(data) == 0:
              return
    finally:
        s.close()

def forward_rtcm(dev, gga):
    path = "/{}".format(MOUNTPOINT)
    accept = "Accept: rtk/rtcm, dgps/rtcm"
    for data in http_stream(path, [accept], gga):
      if debug: print('NTRIP bytes: {}'.format(len(data)))
      dev.write(data)

def init_writer():
  port_counter = 0
  while True:
    try:
      dev = ublox.UBlox(ports[port_counter], baudrate=baudrate, timeout=timeout, panda=panda, grey=grey)
      dev.write("$PUBX,41,1,0039,0003,460800,0*18\r\n")
      return dev
    except serial.serialutil.SerialException as e:
      print(e)
      port_counter = (port_counter + 1)%len(ports)
      time.sleep(2)

def main():
  global ntripRctm

  #context = zmq.Context()
  #gpsNMEA = messaging.sub_sock(context, service_list['gpsNMEA'].port)
  
  dev = init_writer()
  while True:
    try:
        forward_rtcm(dev, "$GPGGA,042304,4145.237762,N,09337.501337,W,2,11,0.6,299.0,M,-33.0,M,,*77")
    except serial.serialutil.SerialException as e:
      print(e)
      dev.close()
      dev = init_writer()
    except socket.error as e:
      print(e)
      time.sleep(1)
    except socket.timeout as e:
      print(e)
      time.sleep(1)

if __name__ == "__main__":
  main()

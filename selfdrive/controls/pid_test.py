#!/usr/bin/env python3
import sys
import time
from selfdrive.controls.lib.pid import PIController

if len(sys.argv) != 2 or sys.argv[1] not in ["lat", "long"]:
  print("  usage: pid_tune.py [lat|long]")
  exit(1)
name = sys.argv[1]

pid = PIController(k_p=0.25, k_i=0.05, pos_limit=1.0, neg_limit=-1.0, rate=100, sat_limit=0.4, name=name)
while True:
  pid.update(1, 2)
  time.sleep(1)

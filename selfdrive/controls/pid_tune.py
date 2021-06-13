#!/usr/bin/env python3
from multiprocessing import shared_memory
import sys
import termios
from termios import (BRKINT, CS8, CSIZE, ECHO, ICANON, ICRNL, IEXTEN, INPCK, ISTRIP, IXON, PARENB, VMIN, VTIME)

import numpy as np

if len(sys.argv) != 2 or sys.argv[1] not in ["lat", "long"]:
  print("  usage: pid_tune.py [lat|long]")
  exit(1)
name = sys.argv[1]
size = 1

k_p_shm = shared_memory.SharedMemory(name=f"pid_{name}_kp")
k_p = np.ndarray((2, size), float, buffer=k_p_shm.buf)
k_i_shm = shared_memory.SharedMemory(name=f"pid_{name}_ki")
k_i = np.ndarray((2, size), float, buffer=k_i_shm.buf)

# Indexes for termios list.
IFLAG = 0
OFLAG = 1
CFLAG = 2
LFLAG = 3
ISPEED = 4
OSPEED = 5
CC = 6

STDIN_FD = sys.stdin.fileno()

def getch() -> str:
  old_settings = termios.tcgetattr(STDIN_FD)
  try:
    # set
    mode = old_settings.copy()
    mode[IFLAG] &= ~(BRKINT | ICRNL | INPCK | ISTRIP | IXON)
    #mode[OFLAG] &= ~(OPOST)
    mode[CFLAG] &= ~(CSIZE | PARENB)
    mode[CFLAG] |= CS8
    mode[LFLAG] &= ~(ECHO | ICANON | IEXTEN)
    mode[CC][VMIN] = 1
    mode[CC][VTIME] = 0
    termios.tcsetattr(STDIN_FD, termios.TCSAFLUSH, mode)

    ch = sys.stdin.read(1)
  finally:
    termios.tcsetattr(STDIN_FD, termios.TCSADRAIN, old_settings)
  return ch

kp_idx = 0
ki_idx = 0
increment = 0.01
while True:
  print(f"kP: i={kp_idx} bp={k_p[0]} v={k_p[1]}\tkI: i={ki_idx} bp={k_i[0]} v={k_i[1]}")
  c = getch()
  # increment contro
  if c == '1':
    increment = 0.1
  elif c == '2':
    increment = 0.01
  elif c == '3':
    increment = 0.001
  # kP control
  elif c == 'w':
    k_p[1][kp_idx] = round(k_p[1][kp_idx] + increment, 3)
  elif c == 's':
    k_p[1][kp_idx] = max(round(k_p[1][kp_idx] - increment, 3), 0.)
  elif c == 'a':
    kp_idx = max(kp_idx-1, 0)
  elif c == 'd':
    kp_idx = min(kp_idx+1, size-1)
  # kI control
  elif c == 'i':
    k_i[1][ki_idx] = round(k_i[1][ki_idx] + increment, 3)
  elif c == 'k':
    k_i[1][ki_idx] = max(round(k_i[1][ki_idx] - increment, 3), 0.)
  elif c == 'j':
    ki_idx = max(ki_idx-1, 0)
  elif c == 'l':
    ki_idx = min(ki_idx+1, size-1)
  elif c == 'q':
    exit(0)

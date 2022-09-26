#!/usr/bin/env python3
from cereal import car
from opendbc.can.parser import CANParser
from selfdrive.car.interfaces import RadarInterfaceBase
from selfdrive.car.hyundai.values import DBC

import math

BLINDSPOT_BUS = 4
BLINDSPOT_METADATA_ADDRS = [0x100, 0x200]
BLINDSPOT_POINTS_ADDRS = [0x101, 0x201]
BLINDSPOT_POINTS_PER_MSG = 5
BLINDSPOT_MAX_POINTS = 65
BLINDSPOT_CHECKSUM_ADDRS = [0x104, 0x204]

def get_radar_can_parser(CP):
  if DBC[CP.carFingerprint]['radar'] is None:
    return None

  signals = []
  checks = []

  for addr in BLINDSPOT_METADATA_ADDRS:
    msg = f"RADAR_POINTS_METADATA_0x{addr:x}"
    signals += [
      ("RADAR_POINT_COUNT", msg),
    ]
    checks += [(msg, 50)]

  for addr in BLINDSPOT_POINTS_ADDRS:
    msg = f"RADAR_POINTS_0x{addr:x}"
    signals += [
      ("MESSAGE_ID", msg),
    ]
    for i in range(BLINDSPOT_POINTS_PER_MSG):
      signals += [
        (f"POINT_{i+1}_DISTANCE", msg),
        (f"POINT_{i+1}_AZIMUTH", msg),
        (f"POINT_{i+1}_REL_VELOCITY", msg),
      ]
    checks += [(msg, 50)]

  for addr in BLINDSPOT_CHECKSUM_ADDRS:
    msg = f"RADAR_POINTS_CHECKSUM_0x{addr:x}"
    signals += [
      ("CRC16", msg),
    ]
    checks += [(msg, 50)]

  return CANParser(DBC[CP.carFingerprint]['radar'], signals, checks, 4)

class RadarInterface(RadarInterfaceBase):
  def __init__(self, CP):
    super().__init__(CP)

    # TODO: add CP.radarBsmOffCan
    #self.radar_off_can = CP.radarOffCan
    self.radar_off_can = False
    self.rcp = get_radar_can_parser(CP)
    self.pts = {addr: list() for addr in BLINDSPOT_POINTS_ADDRS}
    for addr, pts in self.pts.items():
      for _ in range(BLINDSPOT_MAX_POINTS):
        pts.append(car.RadarData.RadarPoint.new_message())
    self.pts_valid = {addr: [0] * BLINDSPOT_MAX_POINTS for addr in BLINDSPOT_POINTS_ADDRS}
    for addr in BLINDSPOT_POINTS_ADDRS:
      self.reset_pts_valid(addr)

  def reset_pts_valid(self, addr, start_idx=0):
    for i in range(start_idx, BLINDSPOT_MAX_POINTS):
      self.pts_valid[addr][i] = False

  def update(self, can_strings):
    if self.radar_off_can or (self.rcp is None):
      return super().update(None)

    self.rcp.update_strings(can_strings)
    # TODO: return nothing if no messages are received? or return last valid points?
    rr = self._update()
    return rr

  def _update(self):
    ret = car.RadarData.new_message()
    if self.rcp is None:
      return ret

    errors = []

    if not self.rcp.can_valid:
      errors.append("canError")
    ret.errors = errors

    for addr, vl in self.rcp.vl_all.items():
      if not vl:
        continue

      if addr in BLINDSPOT_METADATA_ADDRS:
        point_count = int(vl["RADAR_POINT_COUNT"][-1])
        self.reset_pts_valid(addr+1, start_idx=point_count)
        continue

      if addr in BLINDSPOT_POINTS_ADDRS:
        for i in range(len(vl["MESSAGE_ID"])):
          msg_id = int(vl["MESSAGE_ID"][i])
          assert msg_id > 0
          assert msg_id <= BLINDSPOT_MAX_POINTS / BLINDSPOT_POINTS_PER_MSG

          for j in range(BLINDSPOT_POINTS_PER_MSG):
            angle = vl[f"POINT_{j+1}_AZIMUTH"][i]
            distance = vl[f"POINT_{j+1}_DISTANCE"][i]
            rel_velocity = vl[f"POINT_{j+1}_REL_VELOCITY"][i]

            ii = BLINDSPOT_POINTS_PER_MSG * (msg_id - 1) + j
            self.pts[addr][ii].trackId = addr + ii
            # TODO: figure out if the reference point is the front or rear of the car
            self.pts[addr][ii].dRel = -math.cos(angle) * distance
            # TODO: parameterize car width
            car_width_offset = (1.975 / 2) * (1 if addr == BLINDSPOT_POINTS_ADDRS[0] else -1)
            self.pts[addr][ii].yRel = -math.sin(angle) * distance + car_width_offset
            # TODO: check the sign on relative velocity
            self.pts[addr][ii].vRel = rel_velocity
            self.pts[addr][ii].measured = True
            self.pts_valid[addr][ii] = True
            #print(self.pts[addr][ii])

    points_active = list()
    for addr, pts in self.pts.items():
      for i, pt in enumerate(pts):
        if self.pts_valid[addr][i]:
          points_active.append(pt)
    ret.points = points_active

    return ret

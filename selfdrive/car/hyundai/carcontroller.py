from cereal import car
from common.conversions import Conversions as CV
from common.numpy_fast import clip
from common.realtime import DT_CTRL
from opendbc.can.packer import CANPacker
from selfdrive.car import apply_std_steer_torque_limits
from selfdrive.car.hyundai import hyundaicanfd, hyundaican
from selfdrive.car.hyundai.values import HyundaiFlags, Buttons, CarControllerParams, CANFD_CAR, CAR

VisualAlert = car.CarControl.HUDControl.VisualAlert
LongCtrlState = car.CarControl.Actuators.LongControlState


def process_hud_alert(enabled, fingerprint, hud_control):
  sys_warning = (hud_control.visualAlert in (VisualAlert.steerRequired, VisualAlert.ldw))

  # initialize to no line visible
  # TODO: this is not accurate for all cars
  sys_state = 1
  if hud_control.leftLaneVisible and hud_control.rightLaneVisible or sys_warning:  # HUD alert only display when LKAS status is active
    sys_state = 3 if enabled or sys_warning else 4
  elif hud_control.leftLaneVisible:
    sys_state = 5
  elif hud_control.rightLaneVisible:
    sys_state = 6

  # initialize to no warnings
  left_lane_warning = 0
  right_lane_warning = 0
  if hud_control.leftLaneDepart:
    left_lane_warning = 1 if fingerprint in (CAR.GENESIS_G90, CAR.GENESIS_G80) else 2
  if hud_control.rightLaneDepart:
    right_lane_warning = 1 if fingerprint in (CAR.GENESIS_G90, CAR.GENESIS_G80) else 2

  return sys_warning, sys_state, left_lane_warning, right_lane_warning


class CarController:
  def __init__(self, dbc_name, CP, VM):
    self.CP = CP
    self.params = CarControllerParams(CP)
    self.packer = CANPacker(dbc_name)
    self.frame = 0

    self.apply_steer_last = 0
    self.car_fingerprint = CP.carFingerprint
    self.last_button_frame = 0
    self.accel = 0

    self.steer_wind_down = False
    self.stop_timer = 0.0

  def update(self, CC, CS):
    actuators = CC.actuators
    hud_control = CC.hudControl

    # Steering Torque

    # These cars have significantly more torque than most HKG.  Limit to 70% of max.
    steer = actuators.steer
    if self.CP.carFingerprint in (CAR.KONA, CAR.KONA_EV, CAR.KONA_HEV, CAR.KONA_EV_2022):
      steer = clip(steer, -0.7, 0.7)
    new_steer = int(round(steer * self.params.STEER_MAX))
    apply_steer = apply_std_steer_torque_limits(new_steer, self.apply_steer_last, CS.out.steeringTorque, self.params)

    if not CC.latActive:
      apply_steer = 0
      if self.apply_steer_last != 0:
        self.steer_wind_down = True
    if CC.latActive or CS.out.steeringPressed:
      self.steer_wind_down = False

    self.apply_steer_last = apply_steer

    sys_warning, sys_state, left_lane_warning, right_lane_warning = process_hud_alert(CC.enabled, self.car_fingerprint,
                                                                                      hud_control)

    can_sends = []

    if self.CP.carFingerprint in CANFD_CAR:
      # steering control
      can_sends.append(hyundaicanfd.create_lkas(self.packer, self.CP, CC.enabled, CC.latActive, apply_steer))

      # block LFA on HDA2
      if self.frame % 5 == 0 and (self.CP.flags & HyundaiFlags.CANFD_HDA2):
        can_sends.append(hyundaicanfd.create_cam_0x2a4(self.packer, CS.cam_0x2a4))

      # LFA and HDA icons
      if self.frame % 2 == 0 and not (self.CP.flags & HyundaiFlags.CANFD_HDA2):
        can_sends.append(hyundaicanfd.create_lfahda_cluster(self.packer, CC.enabled))

      # button presses
      if (self.frame - self.last_button_frame) * DT_CTRL > 0.25:
        # cruise cancel
        if CC.cruiseControl.cancel:
          if self.CP.flags & HyundaiFlags.CANFD_ALT_BUTTONS:
            can_sends.append(hyundaicanfd.create_cruise_info(self.packer, CS.cruise_info_copy, True))
            self.last_button_frame = self.frame
          else:
            for _ in range(20):
              can_sends.append(hyundaicanfd.create_buttons(self.packer, CS.buttons_counter+1, Buttons.CANCEL))
            self.last_button_frame = self.frame

        # cruise standstill resume
        elif CC.cruiseControl.resume:
          if not (self.CP.flags & HyundaiFlags.CANFD_ALT_BUTTONS):
            can_sends.append(hyundaicanfd.create_buttons(self.packer, CS.buttons_counter+1, Buttons.RES_ACCEL))
            self.last_button_frame = self.frame
    else:

      # tester present - w/ no response (keeps radar disabled)
      if self.CP.openpilotLongitudinalControl:
        if self.frame % 100 == 0:
          can_sends.append([0x7D0, 0, b"\x02\x3E\x80\x00\x00\x00\x00\x00", 0])

      can_sends.append(hyundaican.create_lkas11(self.packer, self.frame, self.car_fingerprint, apply_steer, CC.latActive,
                                     self.steer_wind_down, CS.lkas11, sys_warning, sys_state, CC.enabled,
                                     hud_control.leftLaneVisible, hud_control.rightLaneVisible,
                                     left_lane_warning, right_lane_warning))

      if not self.CP.openpilotLongitudinalControl:
        if CC.cruiseControl.cancel:
          can_sends.append(hyundaican.create_clu11(self.packer, self.frame, CS.clu11, Buttons.CANCEL, self.CP.carFingerprint))
        elif CC.cruiseControl.resume:
          # send resume at a max freq of 10Hz
          if (self.frame - self.last_button_frame) * DT_CTRL > 0.1:
            # send 25 messages at a time to increases the likelihood of resume being accepted
            can_sends.extend([hyundaican.create_clu11(self.packer, self.frame, CS.clu11, Buttons.RES_ACCEL, self.CP.carFingerprint)] * 25)
            self.last_button_frame = self.frame

      if self.frame % 2 == 0 and self.CP.openpilotLongitudinalControl:
        accel = actuators.accel
        jerk_upper = 0
        jerk_lower = 0
        self.stop_timer = self.stop_timer + DT_CTRL if CC.longActive and CS.out.vEgoRaw < 0.05 else 0

        if CC.longActive:
          # TODO: aEgo lags when jerk is high, use smoothed ACCEL_REF_ACC instead?
          accel_error = accel - CS.out.aEgo

          # TODO: jerk upper would probably be better from longitudinal planner desired jerk?
          jerk_upper = clip(2.0 * accel_error, 0.0, 2.0) # zero when error is negative to keep decel control tight
          jerk_lower = 12.7 # always max value to keep decel control tight

          starting_from_hold = self.stop_timer >= 0.25 and actuators.longControlState == LongCtrlState.pid and accel > 0.01 and CS.brake_control_active
          if starting_from_hold:
            # brake controller needs to wind up internallly until it reaches a threshhold where the brakes release
            # larger values cause faster windup (too small and you never start moving)
            # larger values get vehicle moving quicker but can cause sharp negative jerk transitioning back to plan
            # larger values also cause more overshoot and therefore it takes longer to stop once moving
            accel = 1.0
            jerk_upper = 1.0
        accel = clip(accel, CarControllerParams.ACCEL_MIN, CarControllerParams.ACCEL_MAX)

        stopping = CS.out.vEgoRaw < 0.05 and accel <= 0.0
        set_speed_in_units = hud_control.setSpeed * (CV.MS_TO_MPH if CS.clu11["CF_Clu_SPEED_UNIT"] == 1 else CV.MS_TO_KPH)
        can_sends.extend(hyundaican.create_acc_commands(self.packer, CC.enabled, accel, jerk_upper, jerk_lower, int(self.frame / 2),
                                                        hud_control.leadVisible, set_speed_in_units, stopping, CS.out.gasPressed))
        self.accel = accel

      # 20 Hz LFA MFA message
      if self.frame % 5 == 0 and self.car_fingerprint in (CAR.SONATA, CAR.PALISADE, CAR.IONIQ, CAR.KIA_NIRO_EV, CAR.KIA_NIRO_HEV_2021,
                                                          CAR.IONIQ_EV_2020, CAR.IONIQ_PHEV, CAR.KIA_CEED, CAR.KIA_SELTOS, CAR.KONA_EV, CAR.KONA_EV_2022,
                                                          CAR.ELANTRA_2021, CAR.ELANTRA_HEV_2021, CAR.SONATA_HYBRID, CAR.KONA_HEV, CAR.SANTA_FE_2022,
                                                          CAR.KIA_K5_2021, CAR.IONIQ_HEV_2022, CAR.SANTA_FE_HEV_2022, CAR.GENESIS_G70_2020, CAR.SANTA_FE_PHEV_2022):
        can_sends.append(hyundaican.create_lfahda_mfc(self.packer, CC.enabled))

      # 5 Hz ACC options
      if self.frame % 20 == 0 and self.CP.openpilotLongitudinalControl:
        can_sends.extend(hyundaican.create_acc_opt(self.packer))

      # 2 Hz front radar options
      if self.frame % 50 == 0 and self.CP.openpilotLongitudinalControl:
        can_sends.append(hyundaican.create_frt_radar_opt(self.packer))

    new_actuators = actuators.copy()
    new_actuators.steer = apply_steer / self.params.STEER_MAX
    new_actuators.accel = self.accel

    self.frame += 1
    return new_actuators, can_sends

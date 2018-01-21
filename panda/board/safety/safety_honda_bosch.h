// board enforces
//   in-state
//      accel set/resume
//   out-state
//      cancel button
//      accel rising edge
//      brake rising edge
//      brake > 0mph

static void honda_bosch_rx_hook(CAN_FIFOMailBox_TypeDef *to_push) {

  // sample speed
  if ((to_push->RIR>>21) == 0x158) {
    // first 2 bytes
    ego_speed = to_push->RDLR & 0xFFFF;
  }

  // state machine to enter and exit controls
  // 0x1A6 for the ILX, 0x296 for the Civic Touring
  if ((to_push->RIR>>21) == 0x1A6 || (to_push->RIR>>21) == 0x296) {
    int buttons = (to_push->RDLR & 0xE0) >> 5;
    if (buttons == 4 || buttons == 3) {
      controls_allowed = 1;
    } else if (buttons == 2) {
      controls_allowed = 0;
    }
  }

  // exit controls on rising edge of brake press or on brake press when
  // speed > 0
  // if ((to_push->RIR>>21) == 0x17C) {
  //   // bit 53
  //   int brake = to_push->RDHR & 0x200000;
  //   if (brake && (!(brake_prev) || ego_speed)) {
  //     controls_allowed = 0;
  //   }
  //   brake_prev = brake;
  // }

  // exit controls on rising edge of gas press if no interceptor
  // if ((to_push->RIR>>21) == 0x17C) {
  //   int gas = to_push->RDLR & 0xFF;
  //   if (gas && !(gas_prev)) {
  //     controls_allowed = 0;
  //   }
  //   gas_prev = gas;
  // }
}

// all commands: gas, brake and steering
// if controls_allowed and no pedals pressed
//     allow all commands up to limit
// else
//     block all commands that produce actuation

static int honda_bosch_tx_hook(CAN_FIFOMailBox_TypeDef *to_send) {

  // disallow actuator commands if gas or brake (with vehicle moving) are pressed
  // and the the latching controls_allowed flag is True
  int pedal_pressed =  gas_prev || gas_interceptor_prev || (brake_prev && ego_speed);
  int current_controls_allowed = controls_allowed && !(pedal_pressed);

  // STEER: safety check
  if ((to_send->RIR>>21) == 0xE4) {
    if (current_controls_allowed) {
      // all messages are fine here
    } else {
      if ((to_send->RDLR & 0xFFFF0000) != to_send->RDLR) return 0;
    }
  }

  // 1 allows the message through
  return true;
}

static void honda_bosch_init() {
  controls_allowed = 0;
}

const safety_hooks honda_bosch_hooks = {
  .init = honda_bosch_init,
  .rx = honda_bosch_rx_hook,
  .tx = honda_bosch_tx_hook,
};

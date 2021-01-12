#!/usr/bin/env python

# This process publishes joystick events. Such events can be suscribed by
# mocked car controller scripts.


### this process needs pygame and can't run on the EON ###

import pygame  # pylint: disable=import-error
import cereal.messaging as messaging

def joystick_thread():
  joystick_sock = messaging.pub_sock('testJoystick')

  pygame.init()

  # Used to manage how fast the screen updates
  clock = pygame.time.Clock()

  # Initialize the joysticks
  pygame.joystick.init()

  # Get count of joysticks
  joystick_count = pygame.joystick.get_count()
  if joystick_count > 1:
    raise ValueError("More than one joystick attached")
  elif joystick_count < 1:
    #raise ValueError("No joystick found")
    pygame.display.set_mode([200,200])
    print("No joystick found, using keyboard-only mode")

  # -------- Main Program Loop -----------
  while True:
    # EVENT PROCESSING STEP
    for event in pygame.event.get():  # User did something
      if event.type == pygame.QUIT:  # If user clicked close
        pass
      # Available joystick events: JOYAXISMOTION JOYBALLMOTION JOYBUTTONDOWN JOYBUTTONUP JOYHATMOTION
      if event.type == pygame.JOYBUTTONDOWN:
        print("Joystick button pressed.")
      if event.type == pygame.JOYBUTTONUP:
        print("Joystick button released.")
      if event.type == pygame.KEYDOWN:
        print("Key pressed: {}".format(event.key))
      if event.type == pygame.KEYUP:
        print("Key released: {}".format(event.key))

    # Usually axis run in pairs, up/down for one, and left/right for
    # the other.
    axes = []
    buttons = []

    if joystick_count == 0:
      keys=pygame.key.get_pressed()
      axis_0 = 0 # unused
      axis_1 = 0 # brake (+) gas (-) range -1 to 1
      axis_2 = 0 # unused
      axis_3 = 0 # left (+) right (-) range -1 to 1
      button_0 = False # cancel
      button_1 = False # enable
      button_2 = False # beep
      button_3 = False # chime

      if keys[pygame.K_UP]:
        axis_1 = -0.1
      if keys[pygame.K_DOWN]:
        axis_1 = +0.1
      if keys[pygame.K_RIGHT]:
        axis_3 = +1.0
      if keys[pygame.K_LEFT]:
        axis_3 = -1.0
      if keys[pygame.K_ESCAPE]:
        button_0 = True
      if keys[pygame.K_RETURN]:
        button_1 = True

      axes = [axis_0, axis_1, axis_2, axis_3]
      #print(axes)
      buttons = [button_0, button_1, button_2, button_3]
      #print(buttons)
    else:
      joystick = pygame.joystick.Joystick(0)
      joystick.init()

      for a in range(joystick.get_numaxes()):
        axes.append(joystick.get_axis(a))

      for b in range(joystick.get_numbuttons()):
        buttons.append(bool(joystick.get_button(b)))

    dat = messaging.new_message('testJoystick')
    dat.testJoystick.axes = axes
    dat.testJoystick.buttons = buttons
    joystick_sock.send(dat.to_bytes())

    # Limit to 100 frames per second
    clock.tick(100)

if __name__ == "__main__":
  joystick_thread()

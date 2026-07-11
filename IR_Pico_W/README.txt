IR-PicoW  —  UDP IR Bridge for pyVid2-qt
=========================================

HOW IT WORKS
------------
The Pico W receives NEC IR signals from a standard remote control, decodes
them, and forwards the command byte as a UDP packet to one or more Linux
machines running pyVid2-qt.

    IR Remote -> TSOP4838 -> Pico W -> Wi-Fi UDP -> pyVid2-qt (Linux PC)

The ir_rx library (Peter Hinch) handles NEC decoding on GP15. On every
button press, ir_wifi.py looks up the 16-bit NEC address in TARGET_MATRIX
and sends the 8-bit command value (as a decimal string) to the matching
IP address and UDP port. The status LED (GP22) flashes and the buzzer (GP1)
beeps on each successful route.

pyVid2-qt listens on UDP port 5005 by default. If you assign a different
port in TARGET_MATRIX, pass the matching port to pyVid2-qt using the
--udp-port <port> command-line argument.


HARDWARE REQUIREMENTS
---------------------
  - Raspberry Pi Pico W (must be the W variant for Wi-Fi)
  - TSOP4838 IR receiver module (or any 38 kHz demodulating IR receiver)
  - Passive buzzer on GP1
  - Status LED on GP22


WIRING — IR RECEIVER (TSOP4838)
---------------------------------
  IR Module Pin    Pico W Pin
  -----------------------------------
  Pin 1  (OUT)     Pin 20  (GP15)
  Pin 2  (GND)     Pin 18  (GND)
  Pin 3  (3.3 V)   Pin 36  (3V3 OUT)

See TSOP4838.jpg for the module pinout.
See "Raspberry Pi-Pico-W-pinout.png" for Pico W pin numbering.
WARNING: Getting power and ground reversed will destroy the IR module.

Connect the passive buzzer between GP1 (Pin 2) and GND.
Connect the status LED ANODE in series with a 470-Ohm resistor to GP22 (Pin 29) and GND.


SOFTWARE SETUP
--------------
1. Flash MicroPython firmware on the Pico W.

2. Install Thonny IDE and set the interpreter to
   "MicroPython (Raspberry Pi Pico)".

3. Download the ir_rx library from:
   https://github.com/peterhinch/micropython_ir
   Upload the entire ir_rx/ directory to the root of the Pico W.

4. Upload these files to the Pico W root (/):
     main.py
     ir_wifi.py
     Colors.py
     ir_rx/   (entire directory)

   main.py contains only "import ir_wifi". MicroPython runs main.py
   automatically on boot, so the bridge starts without user interaction.


FIRST-TIME SETUP (STEP BY STEP)
--------------------------------
New to the Pico W or MicroPython?  Follow these steps in order.
Getting the bridge working requires two upload passes to the Pico W:
the first to discover your remote's codes, the second to put those
codes into the routing table.

STEP 1 — Wire the hardware
  Wire the TSOP4838, buzzer, and status LED as described in the
  WIRING section above.  Do not power on yet.

STEP 2 — Install the software on the Pico W
  a) Flash MicroPython on the Pico W.
  b) Install Thonny and set the interpreter to:
       MicroPython (Raspberry Pi Pico)
  c) Upload the ir_rx/ library directory to the Pico W.

STEP 3 — First upload: set Wi-Fi, leave TARGET_MATRIX empty
  Open ir_wifi.py and make two changes:

  a) Set your Wi-Fi credentials:
       SSID = "your_ssid"
       PASSWORD = "your_password"

  b) Clear TARGET_MATRIX so nothing is routed yet:
       TARGET_MATRIX = [
           # empty for now
       ]

  Make sure DEBUG = True (it is by default).

  Upload all files to the Pico W root using Thonny:
       main.py
       ir_wifi.py
       Colors.py
       ir_rx/

STEP 4 — Discover your remote's address and button codes
  With the Pico W connected to Thonny via USB, open the Shell panel.
  Power-cycle the Pico W.  Wait for:
       System Active. Monitoring pulse train frames...

  Point your remote at the TSOP4838 and press any button.
  The Shell prints one line per press:
       [Extended (True NEC_16)]  Addr: 0x0050  |  Cmd: 0x46

  "Addr" is your remote's NEC address (identifies the remote/mode).
  "Cmd" is the button code (what pyVid2-qt will act on).

  Record the Addr value.  Then press every button you want to use
  and record each Cmd value.

  NOTE: If nothing prints when you press buttons, check your wiring.
  The most common cause is OUT and GND swapped on the IR receiver.

STEP 5 — Second upload: add your remote to TARGET_MATRIX
  Open ir_wifi.py again and fill in TARGET_MATRIX using the Addr
  you recorded in Step 4 and the IP address of the pyVid2-qt machine:

       TARGET_MATRIX = [
           ("192.168.0.X", 5005, ["0xYOUR_ADDR"]),
       ]

  Replace 192.168.0.X with your machine's IP address and 0xYOUR_ADDR
  with the Addr value from Step 4.  Keep the "0x" prefix and use
  uppercase hex, for example: "0x0050".

  Upload only ir_wifi.py again (other files have not changed).
  Power-cycle the Pico W.

  Press a button.  You should see a routing line in the Shell:
       Addr: 0x0050 -> Routed payload is: [70 (0x46)] to UDP client on 192.168.0.X:5005

  The LED will flash and the buzzer will beep.  The bridge is working.

STEP 6 — Configure ir_keymap.conf on the host machine
  On the Linux machine running pyVid2-qt, open:
       ~/.local/share/pyVid2-qt/ir_keymap.conf

  Each line maps an action name to a hex button code:
       PLAY_PAUSE:0x46
       PLAY_NEXT:0x48

  Replace the hex values with the Cmd codes you recorded in Step 4.
  See ASSETS/ir_keymap.conf in the main project for all action names.

STEP 7 — Launch pyVid2-qt
  Start pyVid2-qt normally.  If you used a port other than 5005 in
  TARGET_MATRIX, add --udp-port to your launch command:
       pyVid --Paths /mnt/videos --udp-port 5006


CONFIGURATION
-------------

Wi-Fi credentials
  Edit ir_wifi.py and set:
    SSID = "your_ssid"
    PASSWORD = "your_password"

TARGET_MATRIX — the Routing Table
  TARGET_MATRIX maps NEC IR addresses to UDP destinations. Each entry is:

    (target_ip, udp_port, [list_of_allowed_NEC_addresses])

  A universal remote sends a different 16-bit NEC *address* for each mode
  (TV, DVD, AUX, etc.) while the *command* byte identifies the button.
  By listing multiple allowed addresses per entry, you can accept one remote
  across modes, or route different modes to different machines or ports.

  Example from ir_wifi.py:
    ("192.168.0.14", 5005, ["0x0000", "0x0040"]),  # RCA remote, two addresses
    ("192.168.0.5",  5005, ["0x0050"]),             # GE remote, TV mode -> port 5005
    ("192.168.0.5",  5006, ["0xFB0C"]),             # GE remote, DVD mode -> port 5006

  "Punch-through" refers to volume buttons that always transmit using the
  TV-mode address regardless of the current remote mode.

NEC Protocol
  ir_wifi.py uses NEC_16 by default:
    from ir_rx.nec import NEC_16

  NEC_8  — older remotes; high address byte is complement of low byte.
  NEC_16 — extended remotes; both address bytes are independent.
  NEC_16 decodes both types correctly and is the recommended default.


FINDING YOUR REMOTE'S CODES
----------------------------
1. Set DEBUG = True in ir_wifi.py (it is True by default).
2. Open Thonny's Shell panel while the Pico W is running.
3. Press each button and note the Addr and Cmd values printed.
4. Add the address to TARGET_MATRIX.
5. Add the Cmd value to ~/.local/share/pyVid2-qt/ir_keymap.conf on the host.

Debug output format:
  [Extended (True NEC_16)]  Addr: 0x0040  |  Cmd: 0x08
  Addr: 0x0040    -> Routed payload is: [8 (0x08)] to UDP client on 192.168.0.14:5005

See Remote_Codes.txt for a reference listing of codes for the RC-G016
universal remote.


STARTUP BEHAVIOUR
-----------------
On power-up the Pico W:
  1. Connects to Wi-Fi and prints its IP to the serial console.
  2. Initialises the NEC_16 IR decoder on GP15.
  3. Enters an idle loop — all work is done in the ir_callback interrupt.

The bridge runs fully unattended. No host-side daemon or pairing is needed.


FILES
-----
  main.py                       MicroPython entry point (import ir_wifi)
  ir_wifi.py                    IR receiver, TARGET_MATRIX router, UDP sender
  Colors.py                     ANSI colour constants for debug output
  ir_rx/                        Peter Hinch's NEC IR decoder library
  ir_keymap.conf                Default keymap template
  Remote_Codes.txt              Button code reference for RC-G016 remote
  TSOP4838.jpg                  IR module pinout diagram
  Raspberry Pi-Pico-W-pinout.png  Pico W GPIO pinout reference

Pico‑W IR Bridge Setup (Quick Instructions)

ABOUT THE IR RECEIVER MODULE
Just about any IR receiver module will work. I had a few TSOP4838 modules on hand and these work well.
The TSOP4838 modules are cheap and easy to find.  Be very careful when connecting the IR Module to the Pico.
If you get the Ground and 3.3v pins mixed up, you can pretty much say goodbye to the IR Module.  Be very careful if
consulting a manufacturer's datasheet.  It is extremely easy to get the power and ground pins mixed up because
there will likely be a number of different modules documented in the same datasheet and their pinouts are different!
See TSOP4838.jpg for the pinouts of the TSOP4838 module.  Again, this is the module I used.  There are many others out
there that will work fine.

HOW TO CONNECT THE IR RECEIVER MODULE TO THE PICO
Consult "Raspberry Pi-Pico-W-pinout.png" for the pinouts of the Pico. On my Pico I connected the IR Modules as follows:

     IR Module          PICO
    Pin-1 (OUT)     Pin-20 (GP15)
    Pin-2 (GND)     Pin-18 (GND)
    Pin-3 (3.3v)    Pin-36 (3V3 OUT)

By default, the Pico code uses GP15, Pin-20 for the IR receiver's OUT pin.

The Pico‑W runs a small MicroPython script that receives IR codes and forwards them to pyVid2 over UDP.
Requirements

    TSOP4838 IR Receiver Module (see above)

    Raspberry Pi Pico‑W

    MicroPython firmware installed

    Thonny IDE

    ir_rx library by Peter Hinch

1. Open Thonny and connect to the Pico‑W

Select MicroPython (Raspberry Pi Pico) as the interpreter.

2. Upload the IR server files

Copy the following to the Pico’s filesystem:

main.py
ir_wifi.py
ir_rx/   (directory)

Use Thonny’s View → Files panel and “Upload to /”.
3. Edit configuration

Open ir_wifi.py on the Pico and set:

SSID = "your_wifi"
PASSWORD = "your_password"

Select the IR protocol decoder you need:

from ir_rx.nec import NEC_8

4. Reboot the Pico

Press Ctrl+D in Thonny or power‑cycle the device.

The IR WiFi bridge starts automatically and sends decoded IR keycodes to pyVid2.

You will have to edit ir_keymaps.conf to match the codes sent by your remote control.
The ir_keymaps.conf file lives in ~/.local/share.pyVid/ on the computer running pyVid2.


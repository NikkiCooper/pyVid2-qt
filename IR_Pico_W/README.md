# IR-PicoW — UDP IR Bridge for pyVid2-qt

A MicroPython application for the Raspberry Pi Pico W that decodes NEC IR remote signals
and routes them as UDP packets to one or more machines running pyVid2-qt.

---

## Table of Contents

- [How It Works](#how-it-works)
- [Hardware Requirements](#hardware-requirements)
- [Wiring](#wiring)
- [Software Setup](#software-setup)
- [First-Time Setup (Step by Step)](#first-time-setup-step-by-step)
- [Configuration](#configuration)
  - [Wi-Fi Credentials](#wi-fi-credentials)
  - [TARGET\_MATRIX — the Routing Table](#target_matrix--the-routing-table)
  - [NEC Protocol Selection](#nec-protocol-selection)
- [Finding Your Remote's Address Codes](#finding-your-remotes-address-codes)
- [Debug Output](#debug-output)
- [Startup Behaviour](#startup-behaviour)
- [Files](#files)

---

## How It Works

```text
IR Remote  →  TSOP4838  →  Pico W  →  Wi-Fi UDP  →  pyVid2-qt (Linux PC)
```

1. The TSOP4838 IR receiver demodulates the 38 kHz carrier and feeds raw pulses to the Pico W on **GP15**.
2. The `ir_rx` library decodes the NEC pulse train, producing a 16-bit **address** and an 8-bit **command**.
3. `ir_wifi.py` looks up the address in `TARGET_MATRIX` and forwards the command byte (as a decimal string)
   via UDP to the matching IP address and port.
4. pyVid2-qt listens on its UDP port and maps the received value to a player action via `ir_keymap.conf`.

pyVid2-qt listens on UDP port **5005** by default. If you assign a different port in `TARGET_MATRIX`,
pass the matching port to pyVid2-qt with `--udp-port <port>` on the command line.

On every successful route, the status LED (GP22) flashes and a short tone sounds on the buzzer (GP1).

---

## Hardware Requirements

| Part | Notes |
|---|---|
| Raspberry Pi Pico W | Must be the **W** variant (has onboard Wi-Fi) |
| TSOP4838 IR Receiver Module | Any 38 kHz demodulating IR receiver will work |
| Small buzzer (passive) | Connected to GP1 via PWM |
| Status LED | Connected to GP22 |

---

## Wiring

### IR Receiver (TSOP4838)

```text
IR Module Pin    Pico W Pin
─────────────────────────────
Pin 1  (OUT)     Pin 20  (GP15)
Pin 2  (GND)     Pin 18  (GND)
Pin 3  (3.3 V)   Pin 36  (3V3 OUT)
```

> See `TSOP4838.jpg` for the module pinout and `Raspberry Pi-Pico-W-pinout.png` for the Pico W pinout.
> Be careful with polarity — the power and ground pins differ between modules and datasheets.

### Buzzer

Connect a passive buzzer between **GP1** (Pin 2) and **GND**. The firmware drives it at 650 Hz PWM.

### Status LED

Connect the LED ANODE in series with a 470-Ohm resistor to **GP22** (Pin 29) and **GND**.

---

## Software Setup

### 1. Install MicroPython on the Pico W

Download the latest MicroPython `.uf2` for the Pico W from the official site and flash it.

### 2. Install Thonny

[Thonny IDE](https://thonny.org/) is the simplest way to transfer files to the Pico W.
Set the interpreter to **MicroPython (Raspberry Pi Pico)**.

### 3. Install the `ir_rx` library

Download Peter Hinch's [`micropython-ir_rx`](https://github.com/peterhinch/micropython_ir) library.
Upload the entire `ir_rx/` directory to the root of the Pico W filesystem.

### 4. Upload the bridge files

Using Thonny's **View → Files** panel, upload the following to `/` on the Pico W:

```text
main.py
ir_wifi.py
Colors.py
ir_rx/          ← entire directory
```

`main.py` contains a single `import ir_wifi` — MicroPython runs `main.py` automatically on boot,
so the bridge starts without any user interaction.

---

## First-Time Setup (Step by Step)

> This walkthrough is for users new to the Pico W or MicroPython. If you are already comfortable
> with the hardware and just need configuration details, skip to [Configuration](#configuration).

Getting the IR bridge working requires two upload passes to the Pico W — the first to discover your
remote's codes, the second to put those codes into the routing table.

---

### Step 1 — Wire the hardware

Wire the TSOP4838, buzzer, and status LED as described in the [Wiring](#wiring) section above.
Do not power on yet.

---

### Step 2 — Install the software on the Pico W

Follow the [Software Setup](#software-setup) steps:

1. Flash MicroPython on the Pico W.
2. Install Thonny and set the interpreter to **MicroPython (Raspberry Pi Pico)**.
3. Upload the `ir_rx/` library directory to the Pico W.

---

### Step 3 — First upload: set Wi-Fi, leave TARGET\_MATRIX empty

Open `ir_wifi.py` in a text editor and make two changes:

**a) Set your Wi-Fi credentials:**

```python
SSID = "your_ssid"
PASSWORD = "your_password"
```

**b) Clear `TARGET_MATRIX` so nothing is routed yet:**

```python
TARGET_MATRIX = [
    # empty for now — we will fill this in after Step 4
]
```

Make sure `DEBUG = True` (it is by default). Now upload all files to the Pico W root using Thonny:

```text
main.py
ir_wifi.py
Colors.py
ir_rx/
```

---

### Step 4 — Discover your remote's address and button codes

With the Pico W connected to Thonny via USB, open the **Shell** panel at the bottom of the Thonny
window. Power-cycle the Pico W (unplug and replug USB, or press the BOOTSEL button then release).

You should see it connect to Wi-Fi and then print:

```text
System Active. Monitoring pulse train frames...
```

Now point your remote at the TSOP4838 and press any button. The Shell will print one line per press:

```text
[Extended (True NEC_16)]  Addr: 0x0050  |  Cmd: 0x46
```

- **Addr** is your remote's NEC address — this identifies the remote and mode.
- **Cmd** is the button code — this is what pyVid2-qt will act on.

**Record the Addr value.** Then press every button you want to use and record each Cmd value.
Write them down or copy them from the Thonny Shell. See [Debug Output](#debug-output) for details.

> If nothing prints when you press buttons, check your wiring. The most common cause is OUT and GND
> swapped on the IR receiver module.

---

### Step 5 — Second upload: add your remote to TARGET\_MATRIX

Open `ir_wifi.py` again and fill in `TARGET_MATRIX` using the Addr you recorded in Step 4 and the
IP address of the machine running pyVid2-qt:

```python
TARGET_MATRIX = [
    ("192.168.0.X", 5005, ["0xYOUR_ADDR"]),
]
```

Replace `192.168.0.X` with your machine's local IP address and `0xYOUR_ADDR` with the Addr value
from Step 4 (keep the `"0x"` prefix and use uppercase hex, e.g. `"0x0050"`).

Upload only `ir_wifi.py` again (the other files have not changed). Power-cycle the Pico W.

Press a button. You should now see a second routing line in the Shell:

```text
Addr: 0x0050    -> Routed payload is: [70 (0x46)] to UDP client on 192.168.0.X:5005
```

The LED will flash and the buzzer will beep. The bridge is working.

---

### Step 6 — Configure ir\_keymap.conf on the host machine

On the Linux machine running pyVid2-qt, open:

```text
~/.local/share/pyVid2-qt/ir_keymap.conf
```

Each line maps an action name to a hex button code:

```text
PLAY_PAUSE:0x46
PLAY_NEXT:0x48
```

Replace the hex values with the Cmd codes you recorded in Step 4.
See the [ir\_keymap.conf reference](../ASSETS/ir_keymap.conf) for all available action names.

---

### Step 7 — Launch pyVid2-qt

Start pyVid2-qt normally. The IR bridge is ready. If you used a port other than `5005` in
`TARGET_MATRIX`, add `--udp-port <port>` to your launch command:

```bash
pyVid --Paths /mnt/videos --udp-port 5006
```

---

## Configuration

### Wi-Fi Credentials

Edit `ir_wifi.py` and set your network details:

```python
SSID = "your_ssid"
PASSWORD = "your_password"
```

### TARGET\_MATRIX — the Routing Table

`TARGET_MATRIX` is the core of the bridge. It maps NEC IR addresses to UDP destinations.

```python
TARGET_MATRIX = [
    ("192.168.0.14", 5005, ["0x0000", "0x0040"]),
    ("192.168.0.5",  5005, ["0x0050"]),
    ("192.168.0.5",  5006, ["0xFB0C"]),
]
```

Each entry is a tuple: `(target_ip, udp_port, [list_of_allowed_NEC_addresses])`

**Why a list of addresses per entry?**

A universal remote sends a different 16-bit NEC *address* depending on which mode (TV, DVD, AUX, etc.)
it is set to. The *command* byte (the actual button) may be the same, but the address field changes.
Some remotes also exhibit "punch-through" behavior — where volume buttons always broadcast using the TV
address regardless of the current mode.

By listing multiple allowed addresses per entry you can:

- Accept the same remote in different modes on a single machine.
- Route different modes of the same remote to **different machines** or **different ports**.

**Example — one remote, two displays on the same machine:**

```python
# GE Universal Remote
# TV mode (address 0x0050)  → display 0 on port 5005
("192.168.0.5", 5005, ["0x0050"]),
# DVD mode (address 0xFB0C) → display 1 on port 5006
("192.168.0.5", 5006, ["0xFB0C"]),
```

**Adding your own remote:**

1. Set `DEBUG = True` (it already is by default).
2. Point any button at the receiver and read the printed address from the debug output.
3. Add a new entry to `TARGET_MATRIX` with that address and the IP/port of the target machine.

### NEC Protocol Selection

The `ir_rx` library supports both 8-bit and 16-bit NEC variants. The default import in `ir_wifi.py` is:

```python
from ir_rx.nec import NEC_16
```

| Variant | When to use |
|---|---|
| `NEC_8` | Older remotes. The high byte of the address is the bitwise complement of the low byte. |
| `NEC_16` | Modern/extended remotes. Both bytes of the address are independent. |

The debug output tells you which type a received frame is:

```text
[Legacy (NEC_8 Match)]   Addr: 0x0000  |  Cmd: 0x46
[Extended (True NEC_16)] Addr: 0xFB0C  |  Cmd: 0xF6
```

`NEC_16` decodes both variants correctly in most cases and is the recommended default.

---

## Finding Your Remote's Address Codes

1. Set `DEBUG = True` in `ir_wifi.py`.
2. Open Thonny's Shell/REPL panel while the Pico W is running.
3. Press each button you want to map and note the **Addr** and **Cmd** values printed.
4. Add the address to the relevant `TARGET_MATRIX` entry.
5. Add or update the corresponding `Cmd` value in `~/.local/share/pyVid2-qt/ir_keymap.conf` on the
   host machine.

See `Remote_Codes.txt` for a reference listing of codes for the RC-G016 universal remote.

---

## Debug Output

With `DEBUG = True`, every received frame prints one line:

```text
[Extended (True NEC_16)]  Addr: 0x0040  |  Cmd: 0x08
```

When a frame matches a `TARGET_MATRIX` entry and is routed, a second line follows:

```text
Addr: 0x0040    -> Routed payload is: [8 (0x08)] to UDP client on 192.168.0.14:5005
```

Repeat codes (auto-repeat while a button is held) are negative values. They are forwarded to
**all** targets unconditionally so that functions like volume change repeat smoothly.

---

## Startup Behavior

On power-up the Pico W:

1. Connects to the configured Wi-Fi network.
2. Prints its assigned IP address to the serial console.
3. Initialises the NEC_16 IR decoder on GP15.
4. Enters an idle `while True: sleep(1)` loop — all work is done in the `ir_callback` interrupt.

The bridge runs fully unattended. No host-side daemon or pairing is required.

---

## Files

| File | Description |
|---|---|
| `main.py` | MicroPython entry point — just `import ir_wifi` |
| `ir_wifi.py` | IR receiver, TARGET\_MATRIX router, UDP sender |
| `Colors.py` | ANSI colour constants for debug output |
| `ir_rx/` | Peter Hinch's NEC IR decoder library |
| `ir_keymap.conf` | Default keymap template (copy to `~/.local/share/pyVid2-qt/`) |
| `Remote_Codes.txt` | Button code reference for the RC-G016 universal remote |
| `TSOP4838.jpg` | TSOP4838 IR module pinout diagram |
| `Raspberry Pi-Pico-W-pinout.png` | Pico W GPIO pinout reference |

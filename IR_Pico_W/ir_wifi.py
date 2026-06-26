from Colors import *
import network
import socket
import time
from ir_rx.nec import NEC_16
from machine import Pin, PWM
#from machine import *

#
# GP15
IR_PIN = 15
#
# GP22
LED_PIN = 22
#
p1 =  machine.Pin(1)
pwm1 = machine.PWM(p1, freq=650,  duty_u16=0)

status_led = machine.Pin(LED_PIN, machine.Pin.OUT)
status_led.off()
  
# Utualize the Picow's on-board LED.
# The on-board LED on Picow is not connected to a pin on the RP2040, but instead to a GPIO pin on the wireless chip. 
#led = machine.Pin("LED", machine.Pin.OUT)
#led.off()
#led.on()

# Set DEBUG = True for debug output
DEBUG = None
lastIPAddr = '0.0.0.0'

# ----------------------------------------------------------------------
# THE HARDWARE ROUTING MATRIX
# Now accommodates multiple addresses per instance due to "punch-through" 
# and toggle-bit layouts. 
# Structure: ("TARGET_IP", PORT, ["LIST", "OF", "ALLOWED", "HEX_ADDRESSES"])
# ----------------------------------------------------------------------
TARGET_MATRIX = [
    # 1. RCA Remote System (Arch Linux)
    # Includes both the base DVD code (0x0000) and the punched-through TV code (0x0040)
    ("192.168.0.14", 5005, ["0x0000", "0x0040"]),
    
    # 2.  GE Universal remote
    # TV Mode:  Address: 0x0050 Portrait monitor  display 0
    # DVD Mode: Address: 0xFB0C Landscape monitor display 1
    ("192.168.0.5", 5005, ["0x0050"]),
    ("192.168.0.5", 5006, ["0xFB0C"]),
                           

    # 3. Roku / GE Remote System (Ubuntu Linux Multi-Port)
    # Includes the alternating toggle addresses for the streaming setup
    
    #("192.168.0.5",  5005, ["0xC7EA", "0xC0E1", "0x0050"]),
    #("192.168.0.5",  5006, ["0xFB0C"]),
    
]
# ----------------------------------------------------------------------

SSID = "nicks"
PASSWORD = "StevieNicks"

print(f"\n{BOLD}{White_f}IR-Picow{RESET} by{BOLD} {Cyan_f}Nikki Cooper{RESET}\n")
print(f"{BOLD}{OKBLUE}--- PACKET GATEWAY ROUTER CORE INITIALIZING ---{RESET}")

wlan = network.WLAN(network.STA_IF)
wlan.active(True)
wlan.connect(SSID, PASSWORD)

while not wlan.isconnected():
    time.sleep(0.1)
print(f"{BOLD}{OKGREEN}Connected to SSID: {Cyan_f}{SSID}{OKGREEN}. {Yellow_f}Pico-W IP: {Cyan_f}{wlan.ifconfig()[0]}{RESET}")

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

def beep():
    pwm1.duty_u16(65535)	# turn on sound
    time.sleep_ms(125)		# pause for 500ms
    pwm1.duty_u16(0)		# turn off sound
    

def ir_callback(data, addr, ctrl):
    # Quick filter for system repeat codes
    if data < 0:
        msg = str(data).encode()
        for ip, port, _ in TARGET_MATRIX:
            sock.sendto(msg, (ip, port))
        return

    # 1. CALCULATE TELEMETRY INFO FOR DEBUGGING
    low_byte = addr & 0xFF
    high_byte = (addr >> 8) & 0xFF
    
    if (low_byte ^ high_byte) == 0xFF:
        protocol_type = "Legacy (NEC_8 Match)"
    else:
        protocol_type = "Extended (True NEC_16)"

    # Format values for debugging and matching
    incoming_addr_str = f"0x{addr:04X}"
    command_hex = f"0x{data:02X}"

    # DEBUG PRINTOUT:
    # Outputs exactly: [Extended (True NEC_16)]  Addr: 0x0040  |  Cmd: 0x08
    if DEBUG is not None:
        print(f"{BOLD}{White_f}[{Yellow_f}{protocol_type}{White_f}]  Addr: {Cyan_f}{incoming_addr_str}{White_f}  |  Cmd: {Green_f}{command_hex}{RESET}")

    # 2. MATCH AND ROUTE DATA
    # Standardize output string payload as decimal text for client script
    msg = str(data).encode()

    for ip, port, allowed_addresses in TARGET_MATRIX:
        # Strict element check
        if incoming_addr_str in allowed_addresses:
            status_led.on()
            sock.sendto(msg, (ip, port))
            print(f"{BOLD}{White_f}Addr: {Cyan_f}{incoming_addr_str}{White_f}    -> {OKGREEN}Routed payload is: [{Cyan_f}{data} {Light_Cyan_f}({command_hex}){OKGREEN}] to UDP client on {Cyan_f}{ip}:{Light_Yellow_f}{port}{RESET}")
            beep()
            status_led.off()

# Initialize the master driver
ir = NEC_16(Pin(IR_PIN, Pin.IN), ir_callback)

print(f"{BOLD}{White_f}System Active. Monitoring pulse train frames...{RESET}\n")
while True:
    time.sleep(1)
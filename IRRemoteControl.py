#   IRRemoteControl.py Copyright (c) 2026 Nikki Cooper
#
#  This program and the accompanying materials are made available under the
#  terms of the GNU Lesser General Public License, version 3.0 which is available at
#  https://www.gnu.org/licenses/gpl-3.0.html#license-text
#
# IR Remote Control module for receiving IR codes via UDP from Raspberry Pi Pico-w

import socket
import threading
import os
from typing import Dict, Optional, Callable


class IRRemoteControl:
    """
    Handles IR remote control input via UDP socket from Raspberry Pi Pico-w.

    Receives IR codes in NEC_8 format, decodes them using a keymap file,
    and triggers appropriate callback functions for each button press.

    Attributes:
        port (int): UDP port to listen on (default: 5005)
        keymap_file (str): Path to the keymap file
        keymap (Dict[str, str]): Maps IR codes (hex strings) to button names
        reverse_keymap (Dict[str, str]): Maps button names to IR codes
        callbacks (Dict[str, Callable]): Maps button names to callback functions
        running (bool): Controls whether the listener thread is active
        sock (socket.socket): UDP socket for receiving IR codes
        thread (threading.Thread): Background thread for receiving codes
        last_code (str): Last received IR code (for repeat handling)
        repeat_enabled (Dict[str, bool]): Tracks which buttons allow repeating
    """

    def __init__(self, keymap_file: str = None, port: int = 5005, debug: bool = True):
        """
        Initialize IR Remote Control receiver.

        Args:
            keymap_file: Path to the keymap file (defaults to ~/.local/share/pyVid2-qt/ir_keymap.conf)
            port: UDP port to listen on
            debug: Enable debug output
        """
        self.port = port
        self.debug = debug

        # Default to XDG data directory
        if keymap_file is None:
            data_dir = os.path.expanduser("~/.local/share/pyVid2-qt")
            self.keymap_file = os.path.join(data_dir, "ir_keymap.conf")
        else:
            self.keymap_file = os.path.expanduser(keymap_file)

        self.keymap: Dict[str, str] = {}  # code -> button name
        self.reverse_keymap: Dict[str, str] = {}  # button name -> code
        self.callbacks: Dict[str, Callable] = {}
        self.running = False
        self.sock: Optional[socket.socket] = None
        self.thread: Optional[threading.Thread] = None
        self.last_code: Optional[str] = None
        self.repeat_enabled: Dict[str, bool] = {}

        # Load the keymap
        self._load_keymap()

    def _load_keymap(self):
        """Load IR code keymap from file."""
        if not os.path.exists(self.keymap_file):
            print(f"Warning: Keymap file {self.keymap_file} not found")
            return

        with open(self.keymap_file, 'r') as f:
            for line in f:
                line = line.strip()
                # Skip empty lines and comments
                if not line or line.startswith('#'):
                    continue

                # Parse line format: BUTTON_NAME:0xCODE # comment
                if ':' in line:
                    parts = line.split('#')[0].strip()  # Remove comments
                    button_name, code = parts.split(':', 1)
                    button_name = button_name.strip()
                    code = code.strip()

                    # Store bidirectional mapping
                    self.keymap[code] = button_name
                    self.reverse_keymap[button_name] = code

                    if self.debug:
                        print(f"  Loaded: {button_name} -> {code}")

        print(f"IR Remote: Loaded {len(self.keymap)} button mappings from {self.keymap_file}")

    def register_callback(self, button_name: str, callback: Callable, allow_repeat: bool = False):
        """
        Register a callback function for a button.

        Args:
            button_name: Name of the button (from keymap file)
            callback: Function to call when button is pressed
            allow_repeat: Whether to trigger callback on repeat codes (-0x1)
        """
        self.callbacks[button_name] = callback
        self.repeat_enabled[button_name] = allow_repeat

    def _receive_loop(self):
        """Background thread loop for receiving IR codes."""
        while self.running:
            try:
                data, addr = self.sock.recvfrom(1024)
                code = data.decode().strip()
                code = str(hex(int(code)))

                if self.debug:
                    print(f"IR Remote: Received raw={data.decode().strip()}, converted={code}")
                    print(f"IR Remote: Keymap has {len(self.keymap)} entries")
                    if len(self.keymap) > 0:
                        print(f"IR Remote: Sample keymap entry: {list(self.keymap.items())[0]}")

                # Handle repeat code
                if code == "-0x1":
                    if self.last_code:
                        button_name = self.keymap.get(self.last_code)
                        if button_name and self.repeat_enabled.get(button_name, False):
                            callback = self.callbacks.get(button_name)
                            if callback:
                                callback()
                    continue

                # Store this code as last received
                self.last_code = code

                # Look up button name
                button_name = self.keymap.get(code)
                if button_name:
                    # Trigger callback if registered
                    callback = self.callbacks.get(button_name)
                    if callback:
                        if self.debug:
                            print(f"IR Remote: {button_name} ({code})")
                        callback()
                    elif self.debug:
                        print(f"IR Remote: {button_name} ({code}) - No callback registered")
                elif self.debug:
                    print(f"IR Remote: Unknown code {code}")
                    print(f"IR Remote: Available codes: {list(self.keymap.keys())[:5]}...")

            except socket.timeout:
                # This is expected - timeout allows checking self.running for clean shutdown
                continue
            except Exception as e:
                if self.running:
                    print(f"IR Remote error: {e}")

    def start(self):
        """Start listening for IR codes in background thread."""
        if self.running:
            print("IR Remote: Already running")
            return

        try:
            # Create and bind UDP socket
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.sock.bind(("0.0.0.0", self.port))
            self.sock.settimeout(1.0)  # Timeout for clean shutdown

            # Start background thread
            self.running = True
            self.thread = threading.Thread(target=self._receive_loop, daemon=True)
            self.thread.start()

            print(f"IR Remote: Listening on UDP port {self.port}\n")
        except Exception as e:
            print(f"IR Remote: Failed to start - {e}")
            self.running = False

    def stop(self):
        """Stop listening for IR codes and clean up."""
        if not self.running:
            return

        self.running = False

        if self.thread:
            self.thread.join(timeout=2.0)

        if self.sock:
            self.sock.close()

        print("IR Remote: Stopped")

    def get_button_code(self, button_name: str) -> Optional[str]:
        """Get the IR code for a button name."""
        return self.reverse_keymap.get(button_name)

    def get_button_name(self, code: str) -> Optional[str]:
        """Get the button name for an IR code."""
        return self.keymap.get(code)

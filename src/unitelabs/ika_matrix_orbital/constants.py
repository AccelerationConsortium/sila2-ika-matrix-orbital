"""
Device limits and serial parameters of the IKA MATRIX Orbital Delta Plus.

Sources, in order of authority:
  1. IKA operating instructions, "Technical data" and "Interfaces and outputs" (RS 232 section).
  2. The heingroup `ika` driver (`ika.thermoshaker`), which this connector wraps.
"""

ORIGINATOR = "com.gitlab.heingroup"
"""Reverse-domain originator for the features of this connector (gitlab.com/heingroup)."""

# Speed, from the technical data: speed range 0 - 3000 rpm, adjustable minimum 300 rpm, 10 rpm steps.
SPEED_MIN = 0
SPEED_MAX = 3000

# Temperature, from the technical data: setting range 1 - 100 °C, setting resolution 1 K.
TEMPERATURE_MIN = 1.0
TEMPERATURE_MAX = 100.0

# Watchdog, from the "Interfaces and outputs" section: OUT_WD1@n / OUT_WD2@n with n in 20 ... 1500 seconds.
WATCHDOG_TIME_MIN = 20
WATCHDOG_TIME_MAX = 1500

# Serial line, from the "RS 232 interface" section: 9600 bit/s, 7 data bits, even parity, 1 stop bit, no flow control.
BAUDRATE = 9600
BYTESIZE = 7
PARITY = "E"
STOPBITS = 1
READ_TIMEOUT = 2.0
"""Seconds to wait for a reply before treating the device as unresponsive (connector choice, not from the manual)."""

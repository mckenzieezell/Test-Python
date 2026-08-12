#!/usr/bin/env python3
"""
Background listener for the lab's LoRa/TDMA swarm comm system.

Opens a serial connection to whichever board's USB port is plugged into the
companion computer (the master or a slave MKR WAN 1310 — either one prints
tagged lines like the ones below over its native USB Serial), parses the
GPS reports, and keeps the most recent report per module in memory so the
extension's UI/API can read it without touching the serial port directly.

Recognized line formats (all already emitted by the existing firmware):
    RX|TT|TT_GPS|1|3|41.491562,-71.423416,20:15:30      (heard from another module)
    TX|SS_GPS|0|5|41.491562,-71.423416,20:15:30          (logger-bound line)
    [TX] SS_GPS|0|5|41.491562,-71.423416,20:15:30        (this module's own USB debug print)
"""

import re
import threading
import time
from dataclasses import dataclass, field
from typing import Optional

import serial

# ---- Configuration ----
# Adjust to match how the receiver enumerates on the companion computer.
# Run `ls /dev/ttyACM* /dev/ttyUSB*` on the Pi with the board plugged in to check.
SWARM_SERIAL_PORT = "/dev/ttyACM1"
SWARM_BAUD_RATE = 115200
RECONNECT_DELAY_S = 3.0
STALE_AFTER_S = 60.0  # a module older than this is flagged "stale" in the snapshot

GPS_LINE_RE = re.compile(
    r"(?P<module>[A-Za-z]+)_GPS\|"
    r"(?P<addr>\d+)\|"
    r"(?P<counter>\d+)\|"
    r"(?P<lat>-?\d+\.\d+),"
    r"(?P<lon>-?\d+\.\d+),"
    r"(?P<time>\S+)"
)


@dataclass
class ModuleReport:
    module: str
    address: int
    counter: int
    latitude: float
    longitude: float
    utc_time: str
    direction: str = "unknown"  # "tx" = local module's own transmission, "rx" = heard from another module
    last_seen: float = field(default_factory=time.time)


def parse_swarm_line(line: str) -> Optional[ModuleReport]:
    """Extract a ModuleReport from a raw serial line, or None if it doesn't match."""
    match = GPS_LINE_RE.search(line)
    if not match:
        return None

    if line.startswith("RX|"):
        direction = "rx"
    elif line.startswith("TX|") or line.startswith("[TX]"):
        direction = "tx"
    else:
        direction = "unknown"

    return ModuleReport(
        module=match.group("module").upper(),
        address=int(match.group("addr")),
        counter=int(match.group("counter")),
        latitude=float(match.group("lat")),
        longitude=float(match.group("lon")),
        utc_time=match.group("time"),
        direction=direction,
    )


class SwarmListener:
    """Owns the serial port, runs in a background thread, keeps latest-per-module state."""

    def __init__(self, port: str = SWARM_SERIAL_PORT, baud: int = SWARM_BAUD_RATE):
        self.port = port
        self.baud = baud
        self._lock = threading.Lock()
        self._reports: dict[str, ModuleReport] = {}
        self._connected = False
        self._last_error: Optional[str] = None
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        if self._thread is not None:
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=2)
            self._thread = None

    def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                with serial.Serial(self.port, self.baud, timeout=1) as ser:
                    self._connected = True
                    self._last_error = None
                    while not self._stop_event.is_set():
                        raw = ser.readline()
                        if not raw:
                            continue
                        line = raw.decode(errors="ignore").strip()
                        if not line:
                            continue
                        report = parse_swarm_line(line)
                        if report is not None:
                            with self._lock:
                                self._reports[report.module] = report
            except serial.SerialException as exc:
                self._connected = False
                self._last_error = str(exc)
                time.sleep(RECONNECT_DELAY_S)
            except Exception as exc:  # keep the reader thread alive no matter what
                self._connected = False
                self._last_error = str(exc)
                time.sleep(RECONNECT_DELAY_S)

    def snapshot(self) -> dict:
        """Thread-safe read of current state, suitable for returning straight from an API route."""
        now = time.time()
        with self._lock:
            modules = []
            for report in self._reports.values():
                age = now - report.last_seen
                modules.append({
                    "module": report.module,
                    "address": report.address,
                    "counter": report.counter,
                    "latitude": report.latitude,
                    "longitude": report.longitude,
                    "utc_time": report.utc_time,
                    "direction": report.direction,
                    "seconds_ago": round(age, 1),
                    "stale": age > STALE_AFTER_S,
                })
        modules.sort(key=lambda m: m["module"])
        return {
            "connected": self._connected,
            "port": self.port,
            "last_error": self._last_error,
            "modules": modules,
        }


# Single shared instance used across the extension's lifetime
swarm_listener = SwarmListener()

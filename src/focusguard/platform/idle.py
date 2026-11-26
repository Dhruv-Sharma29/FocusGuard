"""Seconds since the last keyboard/mouse input, per OS.

Returns None when the OS gives no answer (Wayland, xprintidle missing, a
failed call). Callers treat None as "not idle" so tracking still works.
"""

from __future__ import annotations

import re
import subprocess
import sys


def get_idle_seconds() -> float | None:
    try:
        if sys.platform == "darwin":
            return _idle_macos()
        if sys.platform == "win32":
            return _idle_windows()
        return _idle_x11()
    except Exception:
        return None


def _idle_macos() -> float | None:
    out = subprocess.run(
        ["ioreg", "-c", "IOHIDSystem", "-d", "4"],
        capture_output=True, text=True, timeout=5, check=False,
    ).stdout
    match = re.search(r'"HIDIdleTime"\s*=\s*(\d+)', out)
    return int(match.group(1)) / 1e9 if match else None


def _idle_windows() -> float:
    import ctypes

    class LASTINPUTINFO(ctypes.Structure):
        _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]

    info = LASTINPUTINFO(ctypes.sizeof(LASTINPUTINFO), 0)
    if not ctypes.windll.user32.GetLastInputInfo(ctypes.byref(info)):  # type: ignore[attr-defined]
        raise OSError("GetLastInputInfo failed")
    # Both values are 32-bit millisecond tick counts; mask handles the 49.7-day wrap.
    ticks = int(ctypes.windll.kernel32.GetTickCount())  # type: ignore[attr-defined]
    return ((ticks - int(info.dwTime)) & 0xFFFFFFFF) / 1000


def _idle_x11() -> float | None:
    # ponytail: needs the xprintidle binary; no answer on Wayland. Add a
    # D-Bus org.gnome.Mutter.IdleMonitor call if Wayland users ask.
    out = subprocess.run(
        ["xprintidle"], capture_output=True, text=True, timeout=5, check=False,
    ).stdout.strip()
    return int(out) / 1000 if out.isdigit() else None

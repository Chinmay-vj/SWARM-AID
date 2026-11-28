"""Peak resident memory of this process on Windows without extra dependencies."""

import ctypes
import sys
from ctypes import wintypes


def peak_rss_mib() -> float:
    """Return -1 when the platform cannot report it."""
    if sys.platform != "win32":
        return -1.0

    class Counters(ctypes.Structure):
        _fields_ = [("cb", wintypes.DWORD), ("faults", wintypes.DWORD)] + [
            (name, ctypes.c_size_t) for name in
            ("peak", "working", "qpp", "qp", "qpnp", "qnp", "page", "peak_page")]

    counters = Counters()
    counters.cb = ctypes.sizeof(counters)
    kernel, psapi = ctypes.windll.kernel32, ctypes.windll.psapi
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD]
    if not psapi.GetProcessMemoryInfo(kernel.GetCurrentProcess(), ctypes.byref(counters),
                                      counters.cb):
        return -1.0
    return float(counters.peak) / 2**20

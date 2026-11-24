"""In-process request metrics. Reset on restart; not a substitute for a metrics backend."""

import statistics
import threading
from collections import Counter, deque


class Metrics:
    def __init__(self, window: int = 5000) -> None:
        self.lock = threading.Lock()
        self.requests: Counter[str] = Counter()
        self.statuses: Counter[int] = Counter()
        self.errors = 0
        self.latencies: deque[float] = deque(maxlen=window)

    def observe(self, route: str, status: int, elapsed_ms: float) -> None:
        with self.lock:
            self.requests[route] += 1
            self.statuses[status] += 1
            if status >= 500:
                self.errors += 1
            self.latencies.append(elapsed_ms)

    def snapshot(self) -> dict[str, object]:
        with self.lock:
            values = sorted(self.latencies)
            total = sum(self.requests.values())

            def pct(p: float) -> float | None:
                return values[min(len(values) - 1, int(p * len(values)))] if values else None

            return {
                "requests_total": total,
                "server_errors": self.errors,
                "status_counts": {str(k): v for k, v in sorted(self.statuses.items())},
                "latency_ms": {
                    "mean": statistics.fmean(values) if values else None,
                    "p50": pct(0.5),
                    "p95": pct(0.95),
                    "p99": pct(0.99),
                    "window": len(values),
                },
                "top_routes": dict(self.requests.most_common(20)),
            }


def process_peak_memory_mb() -> float | None:
    """Peak working set (Windows) or max RSS (POSIX) of this server process."""
    import sys

    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes

        class Counters(ctypes.Structure):
            _fields_ = [
                ("cb", wintypes.DWORD),
                ("PageFaultCount", wintypes.DWORD),
                ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t),
            ]

        kernel32 = ctypes.WinDLL("kernel32")
        psapi = ctypes.WinDLL("psapi")
        kernel32.GetCurrentProcess.restype = wintypes.HANDLE
        psapi.GetProcessMemoryInfo.argtypes = [
            wintypes.HANDLE,
            ctypes.POINTER(Counters),
            wintypes.DWORD,
        ]
        psapi.GetProcessMemoryInfo.restype = wintypes.BOOL
        counters = Counters()
        counters.cb = ctypes.sizeof(Counters)
        process = kernel32.GetCurrentProcess()
        if psapi.GetProcessMemoryInfo(process, ctypes.byref(counters), counters.cb):
            return round(float(counters.PeakWorkingSetSize) / 2**20, 1)
        return None
    try:
        import resource

        return round(float(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss) / 1024, 1)
    except (ImportError, OSError):
        return None

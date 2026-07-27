"""Tiny leveled logger for the dashboard.

Output goes to stdout, which on the ESP32-S3 is the USB serial console, so
`make monitor` / `make debug` show it live. Lines look like:

    [   3.412] I wifi: joined GL-MT300N-V2-231 as 192.168.8.233 (-30 dBm)
    [   3.900] D http: GET api.frankfurter.dev/v1/latest?base=EUR&symbols=JPY

The level can come from config.LOG_LEVEL (via configure()) or be forced from the
command line (via set_level()); a forced level always wins, which is what lets
`make debug` turn on tracing without editing config.py.
"""

import sys
import time

DEBUG = 10
INFO = 20
WARN = 30
ERROR = 40
OFF = 100

_NAMES = {"DEBUG": DEBUG, "INFO": INFO, "WARN": WARN, "ERROR": ERROR,
          "OFF": OFF}
_MARKS = {DEBUG: "D", INFO: "I", WARN: "W", ERROR: "E"}

_level = INFO
_forced = False
_t0 = time.ticks_ms()


def set_level(level, force=True):
    """Set the threshold. force=True marks it as an explicit override."""
    global _level, _forced
    if isinstance(level, str):
        level = _NAMES.get(level.strip().upper(), INFO)
    _level = level
    if force:
        _forced = True
    return _level


def configure(level):
    """Apply a configured level unless one was already forced."""
    if not _forced:
        set_level(level, False)
    return _level


def level():
    return _level


def level_name(lvl=None):
    if lvl is None:
        lvl = _level
    for name, value in _NAMES.items():
        if value == lvl:
            return name
    return str(lvl)


def enabled(lvl):
    return lvl >= _level


def uptime_ms():
    return time.ticks_diff(time.ticks_ms(), _t0)


def _stamp():
    ms = uptime_ms()
    return "%4d.%03d" % (ms // 1000, ms % 1000)


def log(lvl, tag, msg, *args):
    if lvl < _level:
        return
    if args:
        try:
            msg = msg % args
        except Exception:
            msg = "%s %s" % (msg, args)
    print("[%s] %s %s: %s" % (_stamp(), _MARKS.get(lvl, "?"), tag, msg))


def debug(tag, msg, *args):
    log(DEBUG, tag, msg, *args)


def info(tag, msg, *args):
    log(INFO, tag, msg, *args)


def warn(tag, msg, *args):
    log(WARN, tag, msg, *args)


def error(tag, msg, *args):
    log(ERROR, tag, msg, *args)


def exception(tag, exc, msg=None, *args):
    """Log an error plus the traceback, which repr() alone would hide."""
    if msg:
        log(ERROR, tag, msg, *args)
    log(ERROR, tag, "%s: %s", type(exc).__name__, exc)
    if _level <= DEBUG:
        sys.print_exception(exc)


def since(t0):
    """Milliseconds elapsed since a time.ticks_ms() sample."""
    return time.ticks_diff(time.ticks_ms(), t0)


def mem(tag, note=""):
    """Log heap usage at DEBUG level."""
    if _level > DEBUG:
        return
    import gc
    free = gc.mem_free()
    alloc = gc.mem_alloc()
    log(DEBUG, tag, "heap %d kB free / %d kB used %s", free // 1024,
        alloc // 1024, note)

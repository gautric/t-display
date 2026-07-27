"""Station-mode Wi-Fi helpers and NTP time sync."""

import time
import network

import log

_TAG = "wifi"
_wlan = None


def station():
    global _wlan
    if _wlan is None:
        _wlan = network.WLAN(network.STA_IF)
    return _wlan


def connect(ssid, password, timeout=25, hostname=None):
    """Bring up the station interface. Raises OSError on timeout."""
    if not ssid:
        raise OSError("no WIFI_SSID configured (see secrets.py)")
    wlan = station()
    wlan.active(True)
    if hostname:
        try:
            wlan.config(hostname=hostname)
            log.debug(_TAG, "hostname %s", hostname)
        except Exception as exc:
            log.debug(_TAG, "hostname not supported: %s", exc)
    # Power save adds seconds of latency to TLS handshakes.
    try:
        wlan.config(pm=network.WLAN.PM_NONE)
        log.debug(_TAG, "power save disabled")
    except Exception as exc:
        log.debug(_TAG, "pm not supported: %s", exc)
    if wlan.isconnected():
        log.debug(_TAG, "already connected as %s", ip())
        return wlan
    log.info(_TAG, "joining %s (timeout %ds)", ssid, timeout)
    t0 = time.ticks_ms()
    wlan.connect(ssid, password)
    deadline = time.ticks_add(t0, int(timeout * 1000))
    while not wlan.isconnected():
        if time.ticks_diff(deadline, time.ticks_ms()) <= 0:
            log.error(_TAG, "timeout joining %s after %d ms, status %s", ssid,
                      log.since(t0), _status())
            wlan.disconnect()
            raise OSError("wifi timeout joining %r" % ssid)
        time.sleep_ms(200)
    log.info(_TAG, "joined %s as %s (%s dBm) in %d ms", ssid, ip(), rssi(),
             log.since(t0))
    log.debug(_TAG, "ifconfig %s", wlan.ifconfig())
    return wlan


def _status():
    try:
        return station().status()
    except Exception:
        return "?"


def ensure(ssid, password, timeout=25, hostname=None):
    """Reconnect if the link dropped. Returns True when connected."""
    wlan = station()
    if wlan.active() and wlan.isconnected():
        return True
    log.warn(_TAG, "link down, reconnecting")
    connect(ssid, password, timeout, hostname)
    return True


def isconnected():
    try:
        return station().isconnected()
    except Exception:
        return False


def ip():
    try:
        if station().isconnected():
            return station().ifconfig()[0]
    except Exception:
        pass
    return None


def rssi():
    try:
        return station().status("rssi")
    except Exception:
        return None


def sync_time(host="pool.ntp.org", retries=3):
    """Set the RTC from NTP (UTC). Returns True on success."""
    try:
        import ntptime
    except ImportError:
        log.warn(_TAG, "ntptime not available in this firmware")
        return False
    ntptime.host = host
    for attempt in range(1, retries + 1):
        t0 = time.ticks_ms()
        try:
            ntptime.settime()
            log.info(_TAG, "clock set from %s in %d ms, utc %s", host,
                     log.since(t0), time.localtime())
            return True
        except Exception as exc:
            log.warn(_TAG, "ntp attempt %d/%d failed: %r", attempt, retries,
                     exc)
            time.sleep_ms(800)
    return False

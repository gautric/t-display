"""EUR/JPY dashboard for the LilyGO T-Display S3 family.

Left button  (GPIO0 / BOOT) : force a refresh
Right button (GPIO21 or 14) : cycle brightness

Progress is logged to the USB serial console; watch it with `make monitor`, or
`make debug` for per-request and per-frame timings.
"""

import gc
import sys
import time
from machine import Pin

import config
import fx
import httpget
import log
import wifi
from screen import Screen, make_display, buttons
from ui import Dashboard

TAG = "main"
BRIGHTNESS_STEPS = (0xFF, 0xD0, 0x80, 0x30, 0x08)


def _pair():
    return "%s/%s" % (config.BASE, config.QUOTE)


def _banner():
    log.info(TAG, "%s dashboard starting, log level %s", _pair(),
             log.level_name())
    try:
        import os
        uname = os.uname()
        log.info(TAG, "%s %s on %s", uname.sysname, uname.release,
                 uname.machine)
    except Exception:
        pass
    log.info(TAG, "board %s, rotation %d, refresh %ds", config.BOARD,
             config.ROTATION, config.REFRESH_SECONDS)
    log.mem(TAG, "at boot")


def _fetch(state):
    """Refresh the quote in place."""
    wifi.ensure(config.WIFI_SSID, config.WIFI_PASSWORD, config.WIFI_TIMEOUT,
                config.WIFI_HOSTNAME)
    quote = fx.fetch(httpget.get_json, config.BASE, config.QUOTE,
                     config.HISTORY_DAYS)
    state["quote"] = quote
    state["error"] = None
    log.info(TAG, "%s = %s %s, %s, %d history points", _pair(),
             fx.format_rate(quote["rate"]), config.QUOTE,
             fx.format_change(quote) or "no change data",
             len(quote["series"]))
    return quote


def main():
    log.configure(config.LOG_LEVEL)
    _banner()

    display = make_display(config)
    screen = Screen(display, config.BAND_HEIGHT)
    dash = Dashboard(screen.width, screen.height, config.BASE, config.QUOTE,
                     config.TZ_OFFSET)
    state = {"quote": None, "error": None, "ip": None, "rssi": None,
             "refresh_fraction": 0.0}
    log.mem(TAG, "after display init")

    screen.render(lambda p: dash.splash(p, _pair(),
                                       "joining %s" % config.WIFI_SSID))
    try:
        wifi.connect(config.WIFI_SSID, config.WIFI_PASSWORD,
                     config.WIFI_TIMEOUT, config.WIFI_HOSTNAME)
    except Exception as exc:
        state["error"] = "wifi: %s" % exc
        log.exception(TAG, exc, "cannot join %s, running offline",
                      config.WIFI_SSID)

    if wifi.isconnected():
        screen.render(lambda p: dash.splash(p, "clock", config.NTP_HOST))
        if not wifi.sync_time(config.NTP_HOST):
            log.warn(TAG, "clock not set, history and the on-screen time are "
                          "unavailable")

    btn_refresh, btn_bright = buttons(config)
    key_a = Pin(btn_refresh, Pin.IN, Pin.PULL_UP)
    key_b = Pin(btn_bright, Pin.IN, Pin.PULL_UP)
    level = 1
    display.brightness(BRIGHTNESS_STEPS[level])
    log.debug(TAG, "buttons: refresh GPIO%d, brightness GPIO%d", btn_refresh,
              btn_bright)

    wdt = None
    if config.USE_WATCHDOG:
        from machine import WDT
        wdt = WDT(timeout=config.WATCHDOG_TIMEOUT * 1000)
        log.info(TAG, "watchdog armed at %ds", config.WATCHDOG_TIMEOUT)

    period = config.REFRESH_SECONDS * 1000
    due = time.ticks_ms()
    started = due
    cycle = 0

    while True:
        if time.ticks_diff(time.ticks_ms(), due) >= 0:
            cycle += 1
            log.debug(TAG, "refresh cycle %d", cycle)
            screen.render(lambda p: dash.draw(p, _busy(state)))
            try:
                _fetch(state)
                period = config.REFRESH_SECONDS * 1000
            except Exception as exc:
                state["error"] = repr(exc)
                period = config.RETRY_SECONDS * 1000
                log.exception(TAG, exc, "fetch failed, retrying in %ds",
                              config.RETRY_SECONDS)
            started = time.ticks_ms()
            due = time.ticks_add(started, period)
            gc.collect()
            log.mem(TAG, "after cycle %d" % cycle)

        state["ip"] = wifi.ip()
        state["rssi"] = wifi.rssi()
        elapsed = time.ticks_diff(time.ticks_ms(), started)
        state["refresh_fraction"] = 1.0 - min(1.0, elapsed / period)
        screen.render(lambda p: dash.draw(p, state))

        deadline = time.ticks_add(time.ticks_ms(), config.TICK_SECONDS * 1000)
        while time.ticks_diff(deadline, time.ticks_ms()) > 0:
            if not key_a.value():
                log.info(TAG, "refresh button pressed")
                due = time.ticks_ms()
                while not key_a.value():
                    time.sleep_ms(20)
                break
            if not key_b.value():
                level = (level + 1) % len(BRIGHTNESS_STEPS)
                log.info(TAG, "brightness 0x%02x", BRIGHTNESS_STEPS[level])
                display.brightness(BRIGHTNESS_STEPS[level])
                while not key_b.value():
                    time.sleep_ms(20)
            if wdt:
                wdt.feed()
            time.sleep_ms(50)
        if wdt:
            wdt.feed()


def _busy(state):
    busy = state.copy()
    busy["refresh_fraction"] = 1.0
    return busy


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log.info(TAG, "stopped from the console")
    except Exception as exc:
        log.exception(TAG, exc, "dashboard crashed")
        sys.print_exception(exc)
        raise

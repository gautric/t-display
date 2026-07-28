"""EUR/JPY dashboard for the LilyGO T-Display S3 family.

Left button  (GPIO0 / BOOT) : refresh, moving to the next menu entry - every
                              pair in config.PAIRS, then the network view, then
                              the two clocks
                              (EUR/USD -> EUR/JPY -> NETWORK -> ANALOG ->
                               DIGITAL -> ...)
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
import ipinfo
import log
import wifi
from screen import Screen, make_display, buttons
from ui import Chrome, VIEW_FX, VIEW_NET, VIEW_ANALOG, VIEW_DIGITAL

TAG = "main"
BRIGHTNESS_STEPS = (0xFF, 0xD0, 0x80, 0x30, 0x08)

# views that show the time instead of fetched data: no quote to poll, but they
# repaint every second and re-sync the RTC now and then
_CLOCKS = (VIEW_ANALOG, VIEW_DIGITAL)

_LABELS = {VIEW_NET: "NETWORK", VIEW_ANALOG: "ANALOG",
           VIEW_DIGITAL: "DIGITAL"}


def _menu():
    """The menu the left button walks: pairs, network view, then the clocks.

    Entries are (view, base, quote); a view that is not a pair leaves the two
    currency slots empty.
    """
    pairs = getattr(config, "PAIRS", None) or ((config.BASE, config.QUOTE),)
    entries = [(VIEW_FX, str(b).upper(), str(q).upper()) for b, q in pairs]
    if getattr(config, "SHOW_NETINFO", True):
        entries.append((VIEW_NET, "", ""))
    if getattr(config, "SHOW_CLOCKS", True):
        entries.append((VIEW_ANALOG, "", ""))
        entries.append((VIEW_DIGITAL, "", ""))
    return tuple(entries)


def _start_index(menu):
    """Boot on config.BASE/QUOTE when the menu lists it, else on the first."""
    try:
        return menu.index((VIEW_FX, config.BASE.upper(),
                           config.QUOTE.upper()))
    except ValueError:
        return 0


def _label(entry):
    """'EUR/JPY' for a pair entry, the view name for everything else."""
    if entry[0] == VIEW_FX:
        return "%s/%s" % (entry[1], entry[2])
    return _LABELS.get(entry[0], entry[0].upper())


def _banner(menu, index):
    log.info(TAG, "%s dashboard starting, log level %s", _label(menu[index]),
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
    log.info(TAG, "menu: %s", ", ".join(_label(e) for e in menu))
    log.mem(TAG, "at boot")


def _view(views, chrome, entry):
    """The dashboard for a menu entry, built on first use and then cached.

    The import is lazy so a board that never opens a view pays neither the
    import nor the object. Never called from a render callback.
    """
    kind = entry[0]
    view = views.get(kind)
    if view is None:
        if kind == VIEW_NET:
            from netui import NetDashboard
            view = NetDashboard(chrome)
        elif kind in _CLOCKS:
            seconds = getattr(config, "SHOW_SECONDS", True)
            if kind == VIEW_ANALOG:
                from clockui import AnalogDashboard
                view = AnalogDashboard(chrome, seconds)
            else:
                from clockui import DigitalDashboard
                view = DigitalDashboard(chrome, seconds)
        else:
            from tradeui import TradeDashboard
            view = TradeDashboard(chrome, entry[1], entry[2])
        views[kind] = view
        log.debug(TAG, "built the %s view", kind)
    return view


def _select(state, chrome, views, menu, index):
    """Apply a menu entry, returning the dashboard that renders it."""
    kind, base, quote_ccy = menu[index]
    state["view"] = kind
    state["error"] = None
    chrome.set_menu(index, len(menu))
    view = _view(views, chrome, menu[index])
    if kind == VIEW_FX and (base != state["base"]
                            or quote_ccy != state["quote_ccy"]):
        state["base"] = base
        state["quote_ccy"] = quote_ccy
        # drop the previous pair's numbers, they no longer match the header,
        # the next cycle repopulates them
        state["quote"] = None
        view.set_pair(base, quote_ccy)
    return view


def _period(state):
    """Milliseconds until the next fetch for the selected view.

    ipinfo.io throttles anonymous callers and its answer only moves when the
    ISP hands out a new address, so the network view polls far slower than a
    quote does. A clock view fetches nothing at all; its cycle is just the NTP
    re-sync, slower still.
    """
    view = state["view"]
    if view == VIEW_NET:
        return getattr(config, "NETINFO_SECONDS", 900) * 1000
    if view in _CLOCKS:
        return getattr(config, "CLOCK_SYNC_SECONDS", 3600) * 1000
    return config.REFRESH_SECONDS * 1000


def _tick(state):
    """Milliseconds between repaints of the selected view.

    The clocks sweep a second hand, so they need a one second beat. The data
    views only move when the countdown hairline does.
    """
    if state["view"] in _CLOCKS:
        return getattr(config, "CLOCK_TICK_SECONDS", 1) * 1000
    return config.TICK_SECONDS * 1000


def _fetch(state):
    """Refresh the data behind the selected view in place."""
    wifi.ensure(config.WIFI_SSID, config.WIFI_PASSWORD, config.WIFI_TIMEOUT,
                config.WIFI_HOSTNAME)
    view = state["view"]
    if view == VIEW_NET:
        return _fetch_net(state)
    if view in _CLOCKS:
        return _fetch_clock(state)
    return _fetch_quote(state)


def _fetch_quote(state):
    """Refresh the quote of the selected pair in place."""
    base = state["base"]
    quote_ccy = state["quote_ccy"]
    quote = fx.fetch(httpget.get_json, base, quote_ccy, config.HISTORY_DAYS)
    state["quote"] = quote
    state["error"] = None
    log.info(TAG, "%s/%s = %s %s, %s, %d history points", base, quote_ccy,
             fx.format_rate(quote["rate"]), quote_ccy,
             fx.format_change(quote) or "no change data",
             len(quote["series"]))
    return quote


def _fetch_net(state):
    """Refresh the public address and its location in place."""
    info = ipinfo.fetch(httpget.get_json,
                        getattr(config, "IPINFO_URL", ipinfo.URL))
    state["net"] = info
    state["error"] = None
    log.info(TAG, "public ip %s, %s %s, %s", info["ip"],
             ipinfo.format_place(info) or "unknown city",
             info["country"] or "??",
             ipinfo.format_coords(info) or "no coordinates")
    return info


def _fetch_clock(state):
    """Re-sync the RTC so the clock views stay honest.

    A failed sync is only fatal while the clock has never been set: the views
    have nothing to show then, so raise and let the caller retry soon. Once the
    time is known a miss costs a few seconds of drift, not the screen.
    """
    host = config.NTP_HOST
    ok = wifi.sync_time(host)
    if not ok and not fx.clock_is_set():
        raise OSError("ntp %s did not answer, clock still unset" % host)
    tm = time.localtime(time.time() + config.TZ_OFFSET)
    info = {"source": "ntp %s" % host,
            "date": "synced %02d:%02d" % (tm[3], tm[4]) if ok else "drifting"}
    state["clock"] = info
    state["error"] = None
    log.info(TAG, "clock %s, local time %02d:%02d:%02d",
             "synced with %s" % host if ok else "not synced, using the RTC",
             tm[3], tm[4], tm[5])
    return info


def main():
    log.configure(config.LOG_LEVEL)
    menu = _menu()
    index = _start_index(menu)
    view, base, quote_ccy = menu[index]
    _banner(menu, index)

    display = make_display(config)
    screen = Screen(display, config.BAND_HEIGHT)
    chrome = Chrome(screen.width, screen.height, config.TZ_OFFSET, len(menu),
                    index)
    views = {}
    dash = _view(views, chrome, menu[index])
    # "now" is the epoch every band of a frame shares, so the header clock and
    # a sweeping second hand cannot disagree halfway down the screen
    state = {"quote": None, "net": None, "clock": None, "error": None,
             "ip": None, "rssi": None, "refresh_fraction": 0.0, "base": base,
             "quote_ccy": quote_ccy, "view": view, "now": time.time()}
    log.mem(TAG, "after display init")

    screen.render(lambda p: chrome.splash(p, _label(menu[index]),
                                         "joining %s" % config.WIFI_SSID))
    try:
        wifi.connect(config.WIFI_SSID, config.WIFI_PASSWORD,
                     config.WIFI_TIMEOUT, config.WIFI_HOSTNAME)
    except Exception as exc:
        state["error"] = "wifi: %s" % exc
        log.exception(TAG, exc, "cannot join %s, running offline",
                      config.WIFI_SSID)

    if wifi.isconnected():
        screen.render(lambda p: chrome.splash(p, "clock", config.NTP_HOST))
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

    period = _period(state)
    due = time.ticks_ms()
    started = due
    deadline = due
    cycle = 0

    while True:
        state["now"] = time.time()
        if time.ticks_diff(time.ticks_ms(), due) >= 0:
            cycle += 1
            log.debug(TAG, "refresh cycle %d, %s", cycle, _label(menu[index]))
            screen.render(lambda p: dash.draw(p, _busy(state)))
            try:
                _fetch(state)
                period = _period(state)
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

        # Beat from the previous deadline, not from the end of the render: a
        # 50 ms frame on a 1 s tick would otherwise run slow enough to make the
        # second hand skip. Re-base when a fetch or a button push overran it.
        deadline = time.ticks_add(deadline, _tick(state))
        if time.ticks_diff(deadline, time.ticks_ms()) <= 0:
            deadline = time.ticks_add(time.ticks_ms(), _tick(state))
        while time.ticks_diff(deadline, time.ticks_ms()) > 0:
            if not key_a.value():
                index = (index + 1) % len(menu)
                dash = _select(state, chrome, views, menu, index)
                log.info(TAG, "refresh button pressed, menu %d/%d is now %s",
                         index + 1, len(menu), _label(menu[index]))
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

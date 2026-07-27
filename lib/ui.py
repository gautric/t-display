"""Shared dashboard chrome: header, footer, splash.

What fills the band between the header and the footer is not this module's
business. Every menu entry has its own view module, which pairs this chrome
with exactly one panel:

    tradeui.TradeDashboard -> tradeview.TradeView   one currency pair
    netui.NetDashboard     -> netview.NetView       the ipinfo.io lookup

Keeping them in separate files means a board that never opens the network view
never imports it, and a new view is a new file instead of another branch in
here.

All geometry is derived from the panel size, so the same code lays out the
536x240 AMOLED and the 320x170 LCD. Coordinates are screen-absolute; the
Painter handed to draw() takes care of the band offset.
"""

import time
import gfx
import fx

_UNSET = "--:--"

# Menu entry kinds. main.py owns the menu itself; the chrome only draws a dot
# per entry and each kind maps to one view module.
VIEW_FX = "fx"
VIEW_NET = "net"


class Chrome:
    """The frame every view shares: title bar, status line, countdown."""

    def __init__(self, width, height, tz_offset=0, menu_count=1,
                 menu_index=0):
        self.w = width
        self.h = height
        self.tz = tz_offset
        self.menu_count = menu_count
        self.menu_index = menu_index

        k = height / 240.0
        self.k = k
        wide = width >= 400
        self.wide = wide

        self.pad = max(6, int(10 * k))
        self.s_head = 2 if wide else 1

        self.head_h = int(30 * k)
        self.y_foot = height - int(4 * k) - 10
        self.y_bar = height - 2

    # ------------------------------------------------------------- helpers --
    def _right(self, text, scale):
        return self.w - self.pad - gfx.text_width(text, scale)

    def _clock(self):
        now = time.time()
        if not fx.clock_is_set(now):
            return _UNSET
        tm = time.localtime(now + self.tz)
        return "%02d:%02d" % (tm[3], tm[4])

    def set_menu(self, index, count=None):
        """Move the selected dot."""
        self.menu_index = index
        if count is not None:
            self.menu_count = count

    # -------------------------------------------------------------- header --
    def _menu_dots(self, p, x, y):
        """One dot per menu entry, the selected one filled."""
        if self.menu_count < 2:
            return 0
        r = max(2, int(3 * self.k))
        gap = r + max(2, int(3 * self.k))
        step = 2 * r + gap
        for i in range(self.menu_count):
            cx = x + i * step
            color = gfx.CYAN if i == self.menu_index else gfx.DARK
            p.fill_rect(cx, y, 2 * r, 2 * r, color)
        return self.menu_count * step - gap

    def header(self, p, title, state):
        """Title, menu dots, Wi-Fi bars, clock. Returns the x past the dots."""
        pad = self.pad
        s = self.s_head
        ty = (self.head_h - 8 * s) // 2
        p.text(title, pad, ty, gfx.WHITE, s)

        dots_x = pad + gfx.text_width(title, s) + int(10 * self.k)
        dots_w = self._menu_dots(p, dots_x, ty + 4 * s - max(2, int(3 * self.k)))

        clock = self._clock()
        cx = self._right(clock, s)
        p.text(clock, cx, ty, gfx.GREY, s)

        level = gfx.rssi_level(state.get("rssi")) if state.get("ip") else 0
        bar_h = 8 * s
        bar_w = 4 * (max(2, bar_h // 5) + 1)
        p.wifi_bars(cx - int(10 * self.k) - bar_w,
                    (self.head_h - bar_h) // 2, bar_h, level,
                    gfx.GREEN if level > 1 else gfx.AMBER, gfx.DARK)

        p.hline(pad, self.head_h, self.w - 2 * pad, gfx.DARK)
        return dots_x + dots_w

    # --------------------------------------------------------------- footer --
    def footer(self, p, state, data):
        """Status line and the hairline countdown to the next refresh.

        data is whatever the view was handed. It only has to carry an optional
        "source", "date" and "series", so a quote dict and an ipinfo dict both
        work here.
        """
        pad = self.pad
        y = self.y_foot
        right = state.get("ip") or "offline"
        right_w = gfx.text_width(right, 1)
        p.text(right, self._right(right, 1), y,
               gfx.GREY if state.get("ip") else gfx.RED, 1)

        room = self.w - 2 * pad - right_w - 8
        error = state.get("error")
        if error:
            p.text(gfx.clip_text(error, room // 8), pad, y, gfx.RED, 1)
        else:
            left = ("%s %s" % ((data or {}).get("source", ""),
                               (data or {}).get("date", ""))).strip()
            left = gfx.clip_text(left, room // 8)
            p.text(left, pad, y, gfx.GREY, 1)
            series = (data or {}).get("series") or []
            if len(series) > 1:
                span = "%s - %s" % (fx.format_rate(min(series)),
                                    fx.format_rate(max(series)))
                span_w = gfx.text_width(span, 1)
                x = (self.w - span_w) // 2
                if (x > pad + gfx.text_width(left, 1) + 8
                        and x + span_w < self.w - pad - right_w - 8):
                    p.text(span, x, y, gfx.GREY, 1)

        # time to the next refresh, hairline along the bottom edge
        frac = state.get("refresh_fraction")
        if frac is not None:
            p.fill_rect(0, self.y_bar, self.w, 2, gfx.DARKER)
            p.fill_rect(0, self.y_bar, int(self.w * max(0.0, min(1.0, frac))),
                        2, gfx.BLUE)

    # -------------------------------------------------------------- splash --
    def splash(self, p, title, message=""):
        s = self.s_head
        p.text(title, (self.w - gfx.text_width(title, s)) // 2,
               self.h // 2 - 8 * s, gfx.WHITE, s)
        if message:
            p.text(message, (self.w - gfx.text_width(message, 1)) // 2,
                   self.h // 2 + 4 * s, gfx.CYAN, 1)


class View:
    """A whole screen: the shared chrome wrapped around one panel.

    Subclasses name themselves, pick their own slice out of the state dict and
    draw their panel. draw() does no I/O and no allocation, because the render
    callback runs once per band.
    """

    def __init__(self, chrome):
        self.chrome = chrome

    def title(self):
        """The label shown in the header."""
        raise NotImplementedError

    def data(self, state):
        """The entry of the state dict this view renders."""
        return None

    def panel(self, p, data):
        """Fill the band between the header and the footer."""
        raise NotImplementedError

    def draw(self, p, state):
        data = self.data(state)
        self.panel(p, data)
        self.chrome.header(p, self.title(), state)
        self.chrome.footer(p, state, data)

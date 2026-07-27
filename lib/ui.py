"""Dashboard chrome: header, footer, splash.

The quote readout itself lives in tradeview.TradeView; this module frames it
with the pair label + menu indicator, the clock, the Wi-Fi bars, the status
line and the countdown to the next refresh.

All geometry is derived from the panel size, so the same code lays out the
536x240 AMOLED and the 320x170 LCD. Coordinates are screen-absolute; the
Painter handed to draw() takes care of the band offset.
"""

import time
import gfx
import fx
from tradeview import TradeView

_UNSET = "--:--"


class Dashboard:
    def __init__(self, width, height, base="EUR", quote="JPY", tz_offset=0,
                 pair_count=1, pair_index=0):
        self.w = width
        self.h = height
        self.base = base
        self.quote = quote
        self.tz = tz_offset
        self.pair_count = pair_count
        self.pair_index = pair_index

        k = height / 240.0
        self.k = k
        wide = width >= 400
        self.wide = wide

        self.pad = max(6, int(10 * k))
        self.s_head = 2 if wide else 1

        self.head_h = int(30 * k)
        self.y_foot = height - int(4 * k) - 10
        self.y_bar = height - 2

        self.trade = TradeView(width, height, base, quote, self.pad)

    # ------------------------------------------------------------- helpers --
    def _right(self, text, scale):
        return self.w - self.pad - gfx.text_width(text, scale)

    def _clock(self):
        now = time.time()
        if not fx.clock_is_set(now):
            return _UNSET
        tm = time.localtime(now + self.tz)
        return "%02d:%02d" % (tm[3], tm[4])

    def pair(self):
        return "%s/%s" % (self.base, self.quote)

    def set_pair(self, base, quote, index=None, count=None):
        """Point the dashboard at another pair from the menu."""
        self.base = base
        self.quote = quote
        if index is not None:
            self.pair_index = index
        if count is not None:
            self.pair_count = count
        self.trade.set_pair(base, quote)

    # -------------------------------------------------------------- header --
    def _menu_dots(self, p, x, y):
        """One dot per pair in the menu, the selected one filled."""
        if self.pair_count < 2:
            return 0
        r = max(2, int(3 * self.k))
        gap = r + max(2, int(3 * self.k))
        step = 2 * r + gap
        for i in range(self.pair_count):
            cx = x + i * step
            color = gfx.CYAN if i == self.pair_index else gfx.DARK
            p.fill_rect(cx, y, 2 * r, 2 * r, color)
        return self.pair_count * step - gap

    def _header(self, p, state):
        pad = self.pad
        s = self.s_head
        pair = self.pair()
        ty = (self.head_h - 8 * s) // 2
        p.text(pair, pad, ty, gfx.WHITE, s)

        dots_x = pad + gfx.text_width(pair, s) + int(10 * self.k)
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
    def _footer(self, p, state, quote):
        pad = self.pad
        y = self.y_foot
        right = state.get("ip") or "offline"
        right_w = gfx.text_width(right, 1)
        p.text(right, self._right(right, 1), y,
               gfx.GREY if state.get("ip") else gfx.RED, 1)

        room = self.w - 2 * pad - right_w - 8
        error = state.get("error")
        if error:
            p.text(_clip(error, room // 8), pad, y, gfx.RED, 1)
        else:
            left = ("%s %s" % ((quote or {}).get("source", ""),
                               (quote or {}).get("date", ""))).strip()
            left = _clip(left, room // 8)
            p.text(left, pad, y, gfx.GREY, 1)
            series = (quote or {}).get("series") or []
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

    # ----------------------------------------------------------------- api --
    def draw(self, p, state):
        quote = state.get("quote")
        self._header(p, state)
        self.trade.draw(p, quote)
        self._footer(p, state, quote)

    def splash(self, p, title, message=""):
        s = self.s_head
        p.text(title, (self.w - gfx.text_width(title, s)) // 2,
               self.h // 2 - 8 * s, gfx.WHITE, s)
        if message:
            p.text(message, (self.w - gfx.text_width(message, 1)) // 2,
                   self.h // 2 + 4 * s, gfx.CYAN, 1)


def _clip(text, limit):
    text = str(text)
    return text if len(text) <= limit else text[: max(0, limit - 1)] + "~"

"""Dashboard layout.

All geometry is derived from the panel size, so the same code lays out the
536x240 AMOLED and the 320x170 LCD. Coordinates are screen-absolute; the
Painter handed to draw() takes care of the band offset.
"""

import time
import gfx
import fx

_UNSET = "--:--"


class Dashboard:
    def __init__(self, width, height, base="EUR", quote="JPY", tz_offset=0):
        self.w = width
        self.h = height
        self.base = base
        self.quote = quote
        self.tz = tz_offset

        k = height / 240.0
        self.k = k
        wide = width >= 400
        self.wide = wide

        self.pad = max(6, int(10 * k))
        self.s_head = 2 if wide else 1
        self.s_body = 2 if wide else 1
        self.s_unit = 3 if wide else 2

        self.head_h = int(30 * k)
        self.y_big = int(38 * k)
        self.h_big = int(84 * k)
        self.y_change = int(130 * k)
        self.y_inverse = int(154 * k)
        self.y_spark = int(178 * k)
        self.h_spark = int(42 * k)
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

    # -------------------------------------------------------------- header --
    def _header(self, p, state):
        pad = self.pad
        s = self.s_head
        pair = "%s/%s" % (self.base, self.quote)
        p.text(pair, pad, (self.head_h - 8 * s) // 2, gfx.WHITE, s)

        clock = self._clock()
        cx = self._right(clock, s)
        p.text(clock, cx, (self.head_h - 8 * s) // 2, gfx.GREY, s)

        level = gfx.rssi_level(state.get("rssi")) if state.get("ip") else 0
        bar_h = 8 * s
        bar_w = 4 * (max(2, bar_h // 5) + 1)
        p.wifi_bars(cx - int(10 * self.k) - bar_w,
                    (self.head_h - bar_h) // 2, bar_h, level,
                    gfx.GREEN if level > 1 else gfx.AMBER, gfx.DARK)

        p.hline(pad, self.head_h, self.w - 2 * pad, gfx.DARK)

    # --------------------------------------------------------------- value --
    def _value(self, p, quote):
        pad = self.pad
        rate = quote.get("rate") if quote else None
        text = fx.format_rate(rate) if rate else "---.--"
        width = p.seg(text, pad, self.y_big, self.h_big, gfx.CYAN, gfx.GHOST)

        ux = pad + width + int(14 * self.k)
        s = self.s_unit
        if ux + gfx.text_width(self.quote, s) < self.w - pad:
            p.text(self.quote, ux, self.y_big + self.h_big - 8 * s,
                   gfx.WHITE, s)
            label = "per 1 %s" % self.base
            if gfx.text_width(label, 1) + ux < self.w - pad:
                p.text(label, ux, self.y_big, gfx.GREY, 1)

    def _change(self, p, quote):
        pad = self.pad
        s = self.s_body
        change = quote.get("change") if quote else None
        y = self.y_change
        if change is None:
            p.text("no previous close", pad, y, gfx.GREY, s)
            return
        up = change >= 0
        color = gfx.GREEN if up else gfx.RED
        size = 4 * s
        if up:
            p.triangle_up(pad, y + (8 * s - size) // 2, size, color)
        else:
            p.triangle_down(pad, y + (8 * s - size) // 2, size, color)
        p.text(fx.format_change(quote), pad + 2 * size + int(6 * self.k), y,
               color, s)

    def _inverse(self, p, quote):
        inverse = quote.get("inverse") if quote else None
        if inverse is None:
            return
        text = "1 %s = %s %s" % (self.quote, fx.format_rate(inverse),
                                 self.base)
        p.text(text, self.pad, self.y_inverse, gfx.WHITE, self.s_body)

    # ------------------------------------------------------------ sparkline --
    def _spark(self, p, quote):
        series = (quote or {}).get("series") or []
        pad = self.pad
        x = pad
        w = self.w - 2 * pad
        if len(series) < 2:
            p.hline(x, self.y_spark + self.h_spark - 1, w, gfx.DARK)
            p.text("no history", x, self.y_spark + self.h_spark // 2 - 4,
                   gfx.DARK, 1)
            return
        p.sparkline(x, self.y_spark, w, self.h_spark, series, gfx.BLUE,
                    gfx.DARK, gfx.CYAN)
        days = "%dd" % len(series)
        p.text(days, x, self.y_spark - 9, gfx.GREY, 1)

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
        self._value(p, quote)
        self._change(p, quote)
        self._inverse(p, quote)
        self._spark(p, quote)
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

"""Trade view: everything that describes one currency pair.

Extracted from the dashboard chrome (header / footer / splash, see ui.py) so
the quote readout can be laid out, reused and reasoned about on its own. The
view owns the vertical band between the header and the footer:

    big rate + unit      the current quote, seven-segment digits
    change               absolute + percent move since the previous close
    inverse              the same rate the other way round
    sparkline            the history window returned by fx.fetch()

The rate and the change line share one colour so the readout cannot contradict
itself: white when the rate is unchanged (or no previous close is known), green
when it moved up, red when it moved down.

Geometry is derived from the panel height, so the same code fits the 536x240
AMOLED and the 320x170 LCD. Coordinates are screen-absolute; the Painter
handed to draw() applies the band offset.
"""

import gfx
import fx


class TradeView:
    def __init__(self, width, height, base="EUR", quote="JPY", pad=None):
        self.w = width
        self.h = height
        self.base = base
        self.quote = quote

        k = height / 240.0
        self.k = k
        self.wide = width >= 400

        self.pad = pad if pad is not None else max(6, int(10 * k))
        self.s_body = 2 if self.wide else 1
        self.s_unit = 3 if self.wide else 2

        self.y_big = int(38 * k)
        self.h_big = int(84 * k)
        self.y_change = int(130 * k)
        self.y_inverse = int(154 * k)
        self.y_spark = int(178 * k)
        self.h_spark = int(42 * k)

    # ----------------------------------------------------------------- pair --
    def set_pair(self, base, quote):
        self.base = base
        self.quote = quote

    def pair(self):
        return "%s/%s" % (self.base, self.quote)

    # -------------------------------------------------------------- colour --
    def _trend_color(self, quote):
        """White when flat or unknown, green when up, red when down."""
        change = quote.get("change") if quote else None
        if not change:  # None or exactly 0.0
            return gfx.WHITE
        return gfx.GREEN if change > 0 else gfx.RED

    # --------------------------------------------------------------- value --
    def _value(self, p, quote):
        pad = self.pad
        rate = quote.get("rate") if quote else None
        text = fx.format_rate(rate) if rate else "---.--"
        width = p.seg(text, pad, self.y_big, self.h_big,
                      self._trend_color(quote), gfx.GHOST)

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
        color = self._trend_color(quote)
        size = 4 * s
        # a flat rate gets no arrow, otherwise white digits next to a green
        # triangle would read as a move
        if change > 0:
            p.triangle_up(pad, y + (8 * s - size) // 2, size, color)
        elif change < 0:
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

    # ----------------------------------------------------------------- api --
    def draw(self, p, quote):
        self._value(p, quote)
        self._change(p, quote)
        self._inverse(p, quote)
        self._spark(p, quote)

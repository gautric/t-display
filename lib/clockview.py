"""Clock panels: an analog dial and a big digital readout.

Both live in one module because they share the only genuinely awkward part of
showing the time on this board: knowing whether there is a time at all. The RTC
starts at the MicroPython epoch and only becomes meaningful once
wifi.sync_time() has landed, so local() returns None until then and both panels
draw a placeholder rather than a plausible but wrong time.

The dial is integer-only. gfx.radial() takes a 60ths-of-a-turn step, so a
minute or a second is already an angle and no float trig runs per frame.

Geometry is derived from the panel size, so the same code fits the 536x240
AMOLED and the 320x170 LCD in either rotation. Coordinates are screen-absolute;
the Painter handed to draw() applies the band offset.
"""

import time

from micropython import const

import fx
import gfx

_DAYS = ("MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN")
_MONTHS = ("JAN", "FEB", "MAR", "APR", "MAY", "JUN",
           "JUL", "AUG", "SEP", "OCT", "NOV", "DEC")

_NO_TIME = "--:--"
_NO_DATE = "clock not set"

# Where the hands park while the clock is unset: the shop-window 10:10, dimmed.
# It reads as a clock at a glance without pretending to be the time.
_IDLE_HOUR = const(50)  # (10 % 12) * 5 + 10 // 12
_IDLE_MIN = const(10)


# ------------------------------------------------------------------ time -----
def local(now=None, tz=0):
    """The local time tuple, or None while the clock has not been set."""
    if now is None:
        now = time.time()
    if not fx.clock_is_set(now):
        return None
    return time.localtime(now + tz)


def format_time(tm, seconds=False):
    """'14:03' / '14:03:27', or '--:--' when there is no time yet."""
    if tm is None:
        return _NO_TIME
    if seconds:
        return "%02d:%02d:%02d" % (tm[3], tm[4], tm[5])
    return "%02d:%02d" % (tm[3], tm[4])


def format_date(tm):
    """'MON 27 JUL 2026', or a note that the clock is unset."""
    if tm is None:
        return _NO_DATE
    return "%s %02d %s %04d" % (_DAYS[tm[6]], tm[2], _MONTHS[tm[1] - 1],
                                tm[0])


def format_zone(tz):
    """'UTC' or 'UTC+02:00' for the configured display offset."""
    if not tz:
        return "UTC"
    minutes = abs(int(tz)) // 60
    return "UTC%s%02d:%02d" % ("-" if tz < 0 else "+", minutes // 60,
                               minutes % 60)


def _hour_step(tm):
    """The hour hand as a 60ths-of-a-turn step, advanced by the minutes."""
    return ((tm[3] % 12) * 5 + tm[4] // 12) % 60


# ---------------------------------------------------------------- analog -----
class AnalogView:
    """A round dial: bezel, ticks, three hands, date block beside it."""

    def __init__(self, width, height, pad=None, tz=0, seconds=True):
        self.w = width
        self.h = height
        self.tz = tz
        self.seconds = seconds

        k = height / 240.0
        self.k = k
        self.wide = width >= 400
        self.pad = pad if pad is not None else max(6, int(10 * k))

        # the dial owns the band between the header and the footer
        top = int(38 * k)
        bottom = height - int(28 * k)
        room_h = bottom - top
        room_w = width - 2 * self.pad
        gap = max(10, int(16 * k))

        r = min(room_h, room_w) // 2
        self.r = r
        self.cy = top + room_h // 2

        # A block of text next to the dial only earns its place when it can
        # hold a readable HH:MM. Otherwise the dial is centred and the date
        # goes underneath, if the panel is tall enough to have a gap there.
        self.side_x = None
        self.under_y = None
        if room_w - 2 * r - gap >= int(150 * k):
            self.cx = self.pad + r
            self.side_x = self.pad + 2 * r + gap
        else:
            self.cx = width // 2
            under = self.cy + r + max(6, int(10 * k))
            if under + 8 <= bottom:
                self.under_y = under

        self.r_hour = r * 52 // 100
        self.r_min = r * 78 // 100
        self.r_sec = r * 88 // 100
        self.r_tail = -(r // 7)  # counterweight behind the second hand
        self.hub = max(3, r // 16)
        self.tick_hour = max(4, r // 8)
        self.tick_min = max(2, r // 20)
        # below this radius the 48 minute ticks smear into the bezel
        self.minutes = r >= 56

        self.s_side = 2 if self.wide else 1
        self.h_side = 0
        if self.side_x is not None:
            room = width - self.pad - self.side_x
            h = int(54 * k)
            while h > 18 and gfx.seg_width("00:00", h) > room:
                h -= 4
            self.h_side = h

    # ---------------------------------------------------------------- face --
    def _face(self, p):
        cx = self.cx
        cy = self.cy
        r = self.r
        p.circle(cx, cy, r, gfx.DARK)
        p.circle(cx, cy, r - 1, gfx.DARK)
        for i in range(60):
            if i % 5 == 0:
                p.radial(cx, cy, i, r - self.tick_hour, r - 2,
                         gfx.CYAN if i % 15 == 0 else gfx.GREY, 2)
            elif self.minutes:
                p.radial(cx, cy, i, r - self.tick_min, r - 2, gfx.DARK)

    # --------------------------------------------------------------- hands --
    def _hands(self, p, tm):
        cx = self.cx
        cy = self.cy
        if tm is None:
            p.radial(cx, cy, _IDLE_HOUR, 0, self.r_hour, gfx.DARK, 4)
            p.radial(cx, cy, _IDLE_MIN, 0, self.r_min, gfx.DARK, 3)
            p.disc(cx, cy, self.hub, gfx.DARK)
            return
        p.radial(cx, cy, _hour_step(tm), 0, self.r_hour, gfx.WHITE, 4)
        p.radial(cx, cy, tm[4], 0, self.r_min, gfx.WHITE, 3)
        if self.seconds:
            p.radial(cx, cy, tm[5], self.r_tail, self.r_sec, gfx.RED, 1)
        p.disc(cx, cy, self.hub, gfx.CYAN)

    # ---------------------------------------------------------------- text --
    def _side(self, p, tm):
        x = self.side_x
        h = self.h_side
        s = self.s_side
        k = self.k
        y = self.cy - h // 2
        p.text(format_zone(self.tz), x, y - int(14 * k), gfx.GREY, 1)
        p.seg(format_time(tm), x, y, h, gfx.CYAN if tm else gfx.DARK,
              gfx.GHOST)
        date = gfx.clip_text(format_date(tm),
                             (self.w - self.pad - x) // (8 * s))
        p.text(date, x, y + h + max(8, int(12 * k)),
               gfx.WHITE if tm else gfx.GREY, s)

    def _under(self, p, tm):
        text = gfx.clip_text(format_date(tm), (self.w - 2 * self.pad) // 8)
        p.text(text, (self.w - gfx.text_width(text, 1)) // 2, self.under_y,
               gfx.GREY, 1)

    # ----------------------------------------------------------------- api --
    def draw(self, p, tm, data=None):
        """Paint the dial for the time tuple tm (None while unset)."""
        self._face(p)
        self._hands(p, tm)
        if self.side_x is not None:
            self._side(p, tm)
        elif self.under_y is not None:
            self._under(p, tm)


# --------------------------------------------------------------- digital -----
class DigitalView:
    """The time as large 7-segment digits, seconds beside it, date below."""

    def __init__(self, width, height, pad=None, tz=0, seconds=True):
        self.w = width
        self.h = height
        self.tz = tz
        self.seconds = seconds

        k = height / 240.0
        self.k = k
        self.wide = width >= 400
        self.pad = pad if pad is not None else max(6, int(10 * k))
        self.s_date = 2 if self.wide else 1

        # the readout owns the band between the header and the footer
        top = int(38 * k)
        bottom = height - int(28 * k)
        gap_label = max(8, int(12 * k))
        gap_date = max(10, int(16 * k))
        spare = bottom - top - 8 - gap_label - gap_date - 8 * self.s_date

        # start from the tallest digits the panel can hold, then shrink until
        # the group fits both ways, so a rotated portrait panel still works
        h = min(int(112 * k), spare)
        room = width - 2 * self.pad
        while h > 24 and self._group(h) > room:
            h -= 4
        self.h_big = h
        self.h_sec = h // 2

        # centre the whole block vertically rather than pin it to the top, so
        # a tall narrow panel does not leave the bottom two thirds empty
        block = 8 + gap_label + h + gap_date + 8 * self.s_date
        self.y_label = top + max(0, (bottom - top - block) // 2)
        self.y_big = self.y_label + 8 + gap_label
        self.y_date = self.y_big + h + gap_date

    def _gap(self, h):
        return max(6, h // 8)

    def _group(self, h):
        """Width of HH:MM plus the smaller seconds block."""
        total = gfx.seg_width("00:00", h)
        if self.seconds:
            total += self._gap(h) + gfx.seg_width("00", h // 2)
        return total

    # ----------------------------------------------------------------- api --
    def draw(self, p, tm, data=None):
        """Paint the readout for the time tuple tm (None while unset)."""
        pad = self.pad
        zone = format_zone(self.tz)
        p.text(zone, pad, self.y_label, gfx.GREY, 1)
        label = "local time" if tm else "waiting for ntp"
        x_label = self.w - pad - gfx.text_width(label, 1)
        # a narrow panel has room for the offset or the note, not for both
        if x_label > pad + gfx.text_width(zone, 1) + 8:
            p.text(label, x_label, self.y_label, gfx.GREY, 1)

        h = self.h_big
        x = (self.w - self._group(h)) // 2
        used = p.seg(format_time(tm), x, self.y_big, h,
                     gfx.CYAN if tm else gfx.DARK, gfx.GHOST)
        if self.seconds:
            p.seg("%02d" % tm[5] if tm else "--", x + used + self._gap(h),
                  self.y_big + h - self.h_sec, self.h_sec,
                  gfx.AMBER if tm else gfx.DARK, gfx.GHOST)

        s = self.s_date
        date = gfx.clip_text(format_date(tm), (self.w - 2 * pad) // (8 * s))
        p.text(date, (self.w - gfx.text_width(date, s)) // 2, self.y_date,
               gfx.WHITE if tm else gfx.GREY, s)

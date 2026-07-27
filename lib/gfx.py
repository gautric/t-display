"""Drawing helpers on top of framebuf: colours, scaled text, 7-segment digits.

Colour convention
-----------------
framebuf.RGB565 stores pixels in the MCU's native byte order (little-endian on
the ESP32) while both panels expect big-endian RGB565 on the wire. rgb() returns
the byte-swapped value, so a framebuf can be blitted to the panel with no
per-pixel fixup.
"""

import framebuf
from micropython import const


def rgb(r, g, b):
    """RGB888 -> byte-swapped RGB565."""
    return ((((g & 0x1C) << 3) | (b >> 3)) << 8) | ((r & 0xF8) | (g >> 5))


BLACK = 0x0000
WHITE = rgb(255, 255, 255)
GREY = rgb(140, 140, 150)
DARK = rgb(40, 40, 48)
DARKER = rgb(20, 20, 26)
GHOST = rgb(10, 14, 20)  # unlit 7-segment strokes
CYAN = rgb(0, 220, 255)
GREEN = rgb(0, 230, 120)
RED = rgb(255, 70, 70)
AMBER = rgb(255, 180, 40)
BLUE = rgb(90, 150, 255)


# ------------------------------------------------------------------- text ----
def text_width(s, scale=1):
    return 8 * scale * len(s)


def clip_text(text, limit):
    """Shorten text to limit characters, marking the cut with a tilde."""
    text = str(text)
    if limit <= 0:
        return ""
    return text if len(text) <= limit else text[:limit - 1] + "~"


def text_scaled(fb, s, x, y, color, scale=1):
    """Draw the built-in 8x8 font scaled by an integer factor.

    Glyphs are rendered once into a 1-bit buffer, then expanded as horizontal
    runs so we issue as few fill_rect calls as possible.
    """
    if scale <= 1:
        fb.text(s, x, y, color)
        return text_width(s, 1)
    w = 8 * len(s)
    mono = framebuf.FrameBuffer(bytearray((w + 7) // 8 * 8), w, 8,
                                framebuf.MONO_HLSB)
    mono.fill(0)
    mono.text(s, 0, 0, 1)
    for row in range(8):
        start = -1
        for col in range(w + 1):
            on = col < w and mono.pixel(col, row)
            if on:
                if start < 0:
                    start = col
            elif start >= 0:
                fb.fill_rect(x + start * scale, y + row * scale,
                             (col - start) * scale, scale, color)
                start = -1
    return w * scale


# -------------------------------------------------------- 7-segment digits ---
# bit order A B C D E F G, A = top bar, G = middle bar
_A = const(0x40)
_B = const(0x20)
_C = const(0x10)
_D = const(0x08)
_E = const(0x04)
_F = const(0x02)
_G = const(0x01)

_GLYPHS = {
    "0": _A | _B | _C | _D | _E | _F,
    "1": _B | _C,
    "2": _A | _B | _D | _E | _G,
    "3": _A | _B | _C | _D | _G,
    "4": _B | _C | _F | _G,
    "5": _A | _C | _D | _F | _G,
    "6": _A | _C | _D | _E | _F | _G,
    "7": _A | _B | _C,
    "8": _A | _B | _C | _D | _E | _F | _G,
    "9": _A | _B | _C | _D | _F | _G,
    "-": _G,
    " ": 0,
    "_": _D,
}

_NARROW = ".,:"


def seg_metrics(h):
    """(digit width, stroke thickness, gap) for a digit box of height h."""
    t = max(2, h // 9)
    w = max(t * 3, int(h * 0.56))
    return w, t, max(2, t)


def seg_width(s, h):
    w, t, gap = seg_metrics(h)
    total = 0
    for ch in s:
        total += (t if ch in _NARROW else w) + gap
    return total - gap if total else 0


def _seg_digit(fb, x, y, w, h, t, mask, color):
    half = (h - 3 * t) // 2
    if mask & _A:
        fb.fill_rect(x + t, y, w - 2 * t, t, color)
    if mask & _F:
        fb.fill_rect(x, y + t, t, half, color)
    if mask & _B:
        fb.fill_rect(x + w - t, y + t, t, half, color)
    if mask & _G:
        fb.fill_rect(x + t, y + t + half, w - 2 * t, t, color)
    if mask & _E:
        fb.fill_rect(x, y + 2 * t + half, t, half, color)
    if mask & _C:
        fb.fill_rect(x + w - t, y + 2 * t + half, t, half, color)
    if mask & _D:
        fb.fill_rect(x + t, y + 2 * t + 2 * half, w - 2 * t, t, color)


def seg_text(fb, s, x, y, h, color, off_color=None):
    """Draw a 7-segment style number. Returns the width consumed.

    off_color, when given, paints the inactive segments (the classic dim LED
    look, which reads very well on a black AMOLED background).
    """
    w, t, gap = seg_metrics(h)
    half = (h - 3 * t) // 2
    cx = x
    for ch in s:
        if ch in _NARROW:
            if ch == ".":
                fb.fill_rect(cx, y + 3 * t + 2 * half - t, t, t, color)
            elif ch == ",":
                fb.fill_rect(cx, y + 3 * t + 2 * half - t, t, t, color)
                fb.fill_rect(cx, y + 3 * t + 2 * half, t, t, color)
            else:  # ':'
                fb.fill_rect(cx, y + t + half // 2, t, t, color)
                fb.fill_rect(cx, y + 2 * t + half + half // 2, t, t, color)
            cx += t + gap
            continue
        mask = _GLYPHS.get(ch, 0)
        if off_color is not None:
            _seg_digit(fb, cx, y, w, h, t, 0x7F & ~mask, off_color)
        _seg_digit(fb, cx, y, w, h, t, mask, color)
        cx += w + gap
    return cx - gap - x if s else 0


# --------------------------------------------------------------- sparkline ---
def sparkline(fb, x, y, w, h, values, color, base_color=None, dot_color=None):
    """Plot values across a w x h box. Auto-scales to min/max."""
    n = len(values)
    if n == 0 or w < 2 or h < 2:
        return
    if base_color is not None:
        fb.hline(x, y + h - 1, w, base_color)
    lo = min(values)
    hi = max(values)
    span = hi - lo
    if span <= 0:
        span = abs(hi) * 0.001 or 1.0
        lo -= span / 2
    px = py = None
    step = (w - 1) / (n - 1) if n > 1 else 0
    for i in range(n):
        cx = x + int(i * step)
        cy = y + (h - 1) - int((values[i] - lo) * (h - 1) / span)
        if px is not None:
            fb.line(px, py, cx, cy, color)
        else:
            fb.pixel(cx, cy, color)
        px, py = cx, cy
    if dot_color is not None and px is not None:
        fb.fill_rect(px - 1, py - 1, 3, 3, dot_color)


# ------------------------------------------------------------------ glyphs ---
def triangle_up(fb, x, y, size, color):
    for i in range(size):
        fb.hline(x + size - 1 - i, y + i, 2 * i + 1, color)


def triangle_down(fb, x, y, size, color):
    for i in range(size):
        fb.hline(x + i, y + i, 2 * (size - i) - 1, color)


def pin(fb, x, y, size, color):
    """Map marker: a blunt round head above a point.

    size is the head radius; the glyph occupies 2*size-1 by 3*size-1 pixels
    from (x, y), the same top-left convention as the triangles. Returns the
    width consumed so a caller can place a label next to it.
    """
    d = 2 * size - 1
    # two overlapping rects read as a circle from three pixels away and cost
    # two fill_rect calls instead of a per-pixel loop
    fb.fill_rect(x + 1, y, d - 2, d, color)
    fb.fill_rect(x, y + 1, d, d - 2, color)
    for i in range(size):
        fb.hline(x + i, y + d + i, d - 2 * i, color)
    return d


def wifi_bars(fb, x, y, h, level, on_color, off_color):
    """4-bar signal indicator. level is 0..4."""
    bw = max(2, h // 5)
    for i in range(4):
        bh = (i + 1) * h // 4
        fb.fill_rect(x + i * (bw + 1), y + h - bh, bw, bh,
                     on_color if i < level else off_color)
    return 4 * (bw + 1)


def rssi_level(rssi):
    if rssi is None:
        return 0
    if rssi >= -55:
        return 4
    if rssi >= -67:
        return 3
    if rssi >= -78:
        return 2
    if rssi >= -90:
        return 1
    return 0

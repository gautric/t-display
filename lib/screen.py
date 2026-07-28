"""Banded framebuffer renderer + display factory.

A full 536x240 RGB565 frame is 251 kB, more than the MicroPython heap on a
board without PSRAM. So the screen is painted in horizontal bands: one buffer is
reused, the whole UI is drawn into it with a negative y offset, and framebuf's
own clipping discards whatever falls outside the band.

Painter wraps the framebuf so UI code never has to remember the offset.
"""

import time

import framebuf
import gfx
import log

_TAG = "screen"


def make_display(cfg):
    """Instantiate the driver named by cfg.BOARD."""
    board = getattr(cfg, "BOARD", "amoled")
    rotation = getattr(cfg, "ROTATION", 1)
    brightness = getattr(cfg, "BRIGHTNESS", 0xD0)
    t0 = time.ticks_ms()
    if board == "amoled":
        baudrate = getattr(cfg, "SPI_BAUDRATE", 40_000_000)
        log.debug(_TAG, "init RM67162, rotation %d, %d MHz, brightness 0x%02x",
                  rotation, baudrate // 1_000_000, brightness)
        from rm67162 import RM67162
        driver = RM67162(rotation=rotation, brightness=brightness,
                         baudrate=baudrate)
    elif board == "lcd":
        log.debug(_TAG, "init ST7789 8-bit parallel, rotation %d", rotation)
        from st7789p8 import ST7789P8, FAST
        if not FAST:
            log.warn(_TAG, "no viper emitter, parallel bus falls back to the "
                           "slow mem32 loop")
        driver = ST7789P8(rotation=rotation, brightness=brightness)
    else:
        raise ValueError("unknown BOARD %r (expected 'amoled' or 'lcd')"
                         % board)
    log.info(_TAG, "%s panel %dx%d ready in %d ms", board, driver.width,
             driver.height, log.since(t0))
    return driver


def buttons(cfg):
    """(left, right) button GPIO numbers for the configured board."""
    return (0, 21) if getattr(cfg, "BOARD", "amoled") == "amoled" else (0, 14)


class Painter:
    """framebuf proxy that shifts every y coordinate by the band offset."""

    __slots__ = ("fb", "dy")

    def __init__(self, fb, dy):
        self.fb = fb
        self.dy = dy

    def pixel(self, x, y, c):
        self.fb.pixel(x, y + self.dy, c)

    def hline(self, x, y, w, c):
        self.fb.hline(x, y + self.dy, w, c)

    def vline(self, x, y, h, c):
        self.fb.vline(x, y + self.dy, h, c)

    def line(self, x0, y0, x1, y1, c):
        self.fb.line(x0, y0 + self.dy, x1, y1 + self.dy, c)

    def rect(self, x, y, w, h, c):
        self.fb.rect(x, y + self.dy, w, h, c)

    def fill_rect(self, x, y, w, h, c):
        self.fb.fill_rect(x, y + self.dy, w, h, c)

    def text(self, s, x, y, c, scale=1):
        return gfx.text_scaled(self.fb, s, x, y + self.dy, c, scale)

    def seg(self, s, x, y, h, c, off_color=None):
        return gfx.seg_text(self.fb, s, x, y + self.dy, h, c, off_color)

    def sparkline(self, x, y, w, h, values, c, base_color=None,
                 dot_color=None):
        gfx.sparkline(self.fb, x, y + self.dy, w, h, values, c, base_color,
                      dot_color)

    def triangle_up(self, x, y, size, c):
        gfx.triangle_up(self.fb, x, y + self.dy, size, c)

    def triangle_down(self, x, y, size, c):
        gfx.triangle_down(self.fb, x, y + self.dy, size, c)

    def pin(self, x, y, size, c):
        return gfx.pin(self.fb, x, y + self.dy, size, c)

    def circle(self, cx, cy, r, c):
        gfx.circle(self.fb, cx, cy + self.dy, r, c)

    def disc(self, cx, cy, r, c):
        gfx.disc(self.fb, cx, cy + self.dy, r, c)

    def radial(self, cx, cy, step, r0, r1, c, weight=1):
        gfx.radial(self.fb, cx, cy + self.dy, step, r0, r1, c, weight)

    def wifi_bars(self, x, y, h, level, on_color, off_color):
        return gfx.wifi_bars(self.fb, x, y + self.dy, h, level, on_color,
                             off_color)


class Screen:
    def __init__(self, driver, band_height=48):
        self.driver = driver
        self.width = driver.width
        self.height = driver.height
        self.band = max(8, min(band_height, self.height))
        self.buf = bytearray(self.width * self.band * 2)
        self.fb = framebuf.FrameBuffer(self.buf, self.width, self.band,
                                       framebuf.RGB565)
        self._view = memoryview(self.buf)
        self.frames = 0
        self.last_ms = 0
        log.debug(_TAG, "%dx%d in %d bands of %d rows, band buffer %d bytes",
                  self.width, self.height,
                  (self.height + self.band - 1) // self.band, self.band,
                  len(self.buf))

    @property
    def brightness(self):
        return self.driver.brightness()

    def set_brightness(self, value):
        self.driver.brightness(value)

    def fill(self, color=gfx.BLACK):
        self.driver.fill(color)

    def render(self, draw, background=gfx.BLACK):
        """Paint the whole screen.

        draw(painter) is called once per band with a Painter whose coordinates
        are screen-absolute.
        """
        t0 = time.ticks_ms()
        y = 0
        w = self.width
        while y < self.height:
            h = min(self.band, self.height - y)
            self.fb.fill(background)
            draw(Painter(self.fb, -y))
            if h == self.band:
                self.driver.blit(0, y, w, h, self.buf)
            else:
                self.driver.blit(0, y, w, h, self._view[: w * h * 2])
            y += h
        self.last_ms = log.since(t0)
        self.frames += 1
        log.debug(_TAG, "frame %d painted in %d ms", self.frames, self.last_ms)

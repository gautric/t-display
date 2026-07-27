"""ST7789 over the 8-bit parallel (i8080) bus of the LilyGO T-Display-S3.

Same wiring as libraries/parallel_io.py in Xinyuan-LilyGO/T-Display-S3-MicroPython,
but the byte loop is driven through the ESP32-S3 GPIO set/clear registers with a
256-entry lookup table instead of per-pin machine.Pin calls, which is what makes
full-screen repaints usable from Python.

Exposes the same surface as rm67162.RM67162 so the rest of the app does not care
which panel it is talking to.
"""

import time
from machine import Pin, PWM, mem32
from micropython import const
from array import array

# --- pin map (T-Display-S3, non AMOLED) -------------------------------------
PIN_POWER_ON = 15
PIN_BL = 38
PIN_RST = 5
PIN_CS = 6
PIN_DC = 7
PIN_WR = 8
PIN_RD = 9
PIN_DATA = (39, 40, 41, 42, 45, 46, 47, 48)

NATIVE_WIDTH = 170
NATIVE_HEIGHT = 320
_OFFSET = 35  # panel is a 240x320 die, the visible 170 columns are centred

_GPIO_OUT_W1TS = const(0x60004008)
_GPIO_OUT_W1TC = const(0x6000400C)
_GPIO_OUT1_W1TS = const(0x60004014)
_GPIO_OUT1_W1TC = const(0x60004018)

_SLPOUT = const(0x11)
_INVON = const(0x21)
_DISPON = const(0x29)
_CASET = const(0x2A)
_RASET = const(0x2B)
_RAMWR = const(0x2C)
_MADCTL = const(0x36)
_COLMOD = const(0x3A)

_MAD_MY = const(0x80)
_MAD_MX = const(0x40)
_MAD_MV = const(0x20)

_INIT = (
    (_SLPOUT, None, 120),
    (_MADCTL, b"\x00", 0),
    (_COLMOD, b"\x55", 0),  # 16 bit/pixel
    (0xB2, b"\x0c\x0c\x00\x33\x33", 0),  # porch
    (0xB7, b"\x35", 0),  # gate control
    (0xBB, b"\x19", 0),  # vcom
    (0xC0, b"\x2c", 0),
    (0xC2, b"\x01", 0),
    (0xC3, b"\x12", 0),  # vrh
    (0xC4, b"\x20", 0),  # vdv
    (0xC6, b"\x0f", 0),  # 60 Hz
    (0xD0, b"\xa4\xa1", 0),
    (0xE0, b"\xd0\x04\x0d\x11\x13\x2b\x3f\x54\x4c\x18\x0d\x0b\x1f\x23", 0),
    (0xE1, b"\xd0\x04\x0c\x11\x13\x2c\x3f\x44\x51\x2f\x1f\x1f\x20\x23", 0),
    (_INVON, None, 0),
    (_DISPON, None, 120),
)

_ROTATIONS = (
    (0x00, False, _OFFSET, 0),
    (_MAD_MY | _MAD_MV, True, 0, _OFFSET),
    (_MAD_MX | _MAD_MY, False, _OFFSET, 0),
    (_MAD_MX | _MAD_MV, True, 0, _OFFSET),
)

try:
    from _fastbus import blast as _blast, blast_repeat as _blast_repeat
    FAST = True
except Exception:  # firmware without the viper emitter
    FAST = False

    def _blast(buf, n, tbl, mask_all, wr_mask):
        for i in range(n):
            s = tbl[buf[i]]
            mem32[_GPIO_OUT1_W1TC] = mask_all ^ s
            mem32[_GPIO_OUT1_W1TS] = s
            mem32[_GPIO_OUT_W1TC] = wr_mask
            mem32[_GPIO_OUT_W1TS] = wr_mask

    def _blast_repeat(buf, n, times, tbl, mask_all, wr_mask):
        for _ in range(times):
            _blast(buf, n, tbl, mask_all, wr_mask)


class ST7789P8:
    """170x320 LCD on an 8-bit parallel bus."""

    def __init__(self, rotation=1, brightness=0xFF, data=PIN_DATA):
        self._power = Pin(PIN_POWER_ON, Pin.OUT, value=1)
        self._rst = Pin(PIN_RST, Pin.OUT, value=1)
        self._cs = Pin(PIN_CS, Pin.OUT, value=1)
        self._dc = Pin(PIN_DC, Pin.OUT, value=1)
        self._wr = Pin(PIN_WR, Pin.OUT, value=1)
        self._rd = Pin(PIN_RD, Pin.OUT, value=1)
        self._data = [Pin(p, Pin.OUT, value=0) for p in data]

        # All eight data lines live above GPIO32, so they share GPIO_OUT1.
        for p in data:
            if p < 32:
                raise ValueError("data pin %d outside GPIO_OUT1" % p)
        self._mask_all = 0
        for p in data:
            self._mask_all |= 1 << (p - 32)
        if PIN_WR >= 32:
            raise ValueError("WR pin outside GPIO_OUT")
        self._wr_mask = 1 << PIN_WR

        # byte value -> GPIO_OUT1 bit pattern
        self._tbl = array("I", bytes(4 * 256))
        for value in range(256):
            bits = 0
            for i, p in enumerate(data):
                if value & (1 << i):
                    bits |= 1 << (p - 32)
            self._tbl[value] = bits

        self._bl = None
        self._rowbuf = None
        self.width = 0
        self.height = 0
        self._xo = 0
        self._yo = 0

        self.reset()
        for cmd, payload, delay in _INIT:
            self._cmd(cmd, payload)
            if delay:
                time.sleep_ms(delay)
        self.rotation(rotation)
        self._bl = PWM(Pin(PIN_BL), freq=5000)
        self.brightness(brightness)

    # --- low level ----------------------------------------------------------
    def _write(self, buf, n=None):
        if n is None:
            n = len(buf)
        _blast(buf, n, self._tbl, self._mask_all, self._wr_mask)

    def _cmd(self, cmd, payload=None):
        self._cs(0)
        self._dc(0)
        self._write(bytes((cmd,)), 1)
        self._dc(1)
        if payload:
            self._write(payload, len(payload))
        self._cs(1)

    def reset(self):
        self._rst(1)
        time.sleep_ms(20)
        self._rst(0)
        time.sleep_ms(50)
        self._rst(1)
        time.sleep_ms(150)

    # --- geometry -----------------------------------------------------------
    def rotation(self, value=None):
        if value is None:
            return self._rot
        self._rot = value & 3
        madctl, landscape, xo, yo = _ROTATIONS[self._rot]
        self._xo = xo
        self._yo = yo
        if landscape:
            self.width, self.height = NATIVE_HEIGHT, NATIVE_WIDTH
        else:
            self.width, self.height = NATIVE_WIDTH, NATIVE_HEIGHT
        self._cmd(_MADCTL, bytes((madctl,)))
        self._rowbuf = None
        return self._rot

    def _window(self, x0, y0, x1, y1):
        x0 += self._xo
        x1 += self._xo
        y0 += self._yo
        y1 += self._yo
        self._cmd(_CASET, bytes((x0 >> 8, x0 & 0xFF, x1 >> 8, x1 & 0xFF)))
        self._cmd(_RASET, bytes((y0 >> 8, y0 & 0xFF, y1 >> 8, y1 & 0xFF)))

    # --- drawing ------------------------------------------------------------
    def blit(self, x, y, w, h, buf):
        if w <= 0 or h <= 0:
            return
        self._window(x, y, x + w - 1, y + h - 1)
        self._cs(0)
        self._dc(0)
        self._write(b"\x2c", 1)
        self._dc(1)
        self._write(buf, w * h * 2)
        self._cs(1)

    def fill_rect(self, x, y, w, h, color):
        if w <= 0 or h <= 0:
            return
        if self._rowbuf is None or len(self._rowbuf) < w * 2:
            self._rowbuf = bytearray(self.width * 2)
        lo = color & 0xFF
        hi = (color >> 8) & 0xFF
        for i in range(0, w * 2, 2):
            self._rowbuf[i] = lo
            self._rowbuf[i + 1] = hi
        self._window(x, y, x + w - 1, y + h - 1)
        self._cs(0)
        self._dc(0)
        self._write(b"\x2c", 1)
        self._dc(1)
        _blast_repeat(self._rowbuf, w * 2, h, self._tbl, self._mask_all,
                      self._wr_mask)
        self._cs(1)

    def fill(self, color=0):
        self.fill_rect(0, 0, self.width, self.height, color)

    # --- panel control ------------------------------------------------------
    def brightness(self, value=None):
        if value is None:
            return 0 if self._bl is None else self._bl.duty_u16() >> 8
        value = max(0, min(255, int(value)))
        if self._bl is not None:
            self._bl.duty_u16(value * 257)
        return value

    def invert(self, on=True):
        self._cmd(_INVON if on else 0x20)

    def on(self):
        self._cmd(_DISPON)
        self.brightness(0xFF)

    def off(self):
        self.brightness(0)
        self._cmd(0x28)

    def sleep(self):
        self.off()
        self._cmd(0x10)

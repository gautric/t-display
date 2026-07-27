"""RM67162 AMOLED driver for the LilyGO T-Display-S3 AMOLED 1.91" v1.0.

The panel hangs off the ESP32-S3 QSPI pins and speaks a SPI-flash-like protocol:
each transaction is a command byte, a 24-bit address holding the register in its
middle byte, then the payload.

    CS low -> 0x02, 0x00, reg, 0x00 -> parameters -> CS high

LilyGO's C code clocks that header over all four data lines, but the panel also
accepts it on D0 alone, which is what makes a pure-MicroPython driver possible:
machine.SPI has no quad mode, yet single-line framing works at full clock speed.
D1..D3 are simply parked high, as a SPI flash would leave them. There is no D/CX
pin in this mode - the 0x02 command is what marks a write.

Verified on hardware: a full-screen fill lands on the whole panel and register
writes take effect. The older 4-wire variant of this driver (D1 used as D/CX)
got no response at all on this board revision.

Pixels are pushed as big-endian RGB565. Use gfx.rgb() to build colours; it
pre-swaps the bytes so a little-endian framebuf.RGB565 buffer can be blitted
straight to the panel.
"""

import time
from machine import Pin, SPI
from micropython import const

# --- pin map (T-Display-S3 AMOLED 1.91" v1.0) -------------------------------
PIN_SCK = 47
PIN_D0 = 18  # QSPI D0, the only data line this driver uses
PIN_D1 = 7  # parked high
PIN_D2 = 48  # parked high
PIN_D3 = 5  # parked high
PIN_CS = 6
PIN_RST = 17
PIN_EN = 38  # PMIC enable, must be high or the panel stays dark

NATIVE_WIDTH = 240
NATIVE_HEIGHT = 536

# --- protocol ---------------------------------------------------------------
_WRITE = const(0x02)  # command byte for "write register"

# --- registers --------------------------------------------------------------
_SLPIN = const(0x10)
_SLPOUT = const(0x11)
_INVOFF = const(0x20)
_INVON = const(0x21)
_DISPOFF = const(0x28)
_DISPON = const(0x29)
_CASET = const(0x2A)
_RASET = const(0x2B)
_RAMWR = const(0x2C)
_TEOFF = const(0x34)
_TEON = const(0x35)
_MADCTL = const(0x36)
_COLMOD = const(0x3A)
_WRDISBV = const(0x51)
_PAGE = const(0xFE)

_MAD_MY = const(0x80)
_MAD_MX = const(0x40)
_MAD_MV = const(0x20)

# (command, payload, delay_ms) - mirrors LilyGO's rm67162_cmd table, the one
# their board table pairs with the QSPI configuration of this board.
_INIT = (
    (_PAGE, b"\x00", 0),  # select page 0
    (_SLPOUT, b"\x00", 130),
    (_PAGE, b"\x05", 0),
    (0x05, b"\x05", 0),  # OVSS, elvss -3.95 V
    (_PAGE, b"\x01", 0),
    (0x73, b"\x25", 0),  # OVSS voltage level -4.0 V
    (_PAGE, b"\x00", 0),
    (_COLMOD, b"\x55", 0),  # 16 bit/pixel
    (_WRDISBV, b"\x00", 0),  # brightness off while initialising
    (_DISPON, b"\x00", 130),
)

# MADCTL value per rotation, and whether that rotation is landscape
_ROTATIONS = (
    (0x00, False),
    (_MAD_MX | _MAD_MV, True),
    (_MAD_MX | _MAD_MY, False),
    (_MAD_MV | _MAD_MY, True),
)


class RM67162:
    """536x240 AMOLED panel, QSPI framing over a single data line."""

    def __init__(
        self,
        spi_id=1,
        sck=PIN_SCK,
        mosi=PIN_D0,
        cs=PIN_CS,
        rst=PIN_RST,
        en=PIN_EN,
        idle=(PIN_D1, PIN_D2, PIN_D3),
        baudrate=40_000_000,
        rotation=1,
        brightness=0xD0,
    ):
        if en is not None:
            self._en = Pin(en, Pin.OUT, value=1)
        else:
            self._en = None
        # D1..D3 are unused in single-line framing but must not float.
        self._idle = [Pin(p, Pin.OUT, value=1) for p in idle]
        self._cs = Pin(cs, Pin.OUT, value=1)
        self._rst = Pin(rst, Pin.OUT, value=1)
        self._spi = SPI(spi_id, baudrate=baudrate, polarity=0, phase=0,
                        sck=Pin(sck), mosi=Pin(mosi))
        self._hdr = bytearray(4)
        self._hdr[0] = _WRITE
        self._rowbuf = None
        self._bl = brightness
        self.width = 0
        self.height = 0
        self.reset()
        self._run_init()
        self.rotation(rotation)
        self.brightness(brightness)

    # --- low level ----------------------------------------------------------
    def _cmd(self, cmd, data=None):
        hdr = self._hdr
        hdr[2] = cmd
        self._cs(0)
        self._spi.write(hdr)
        if data:
            self._spi.write(data)
        self._cs(1)

    def _begin_pixels(self):
        """Open a RAMWR transaction; the caller pushes bytes and closes CS."""
        hdr = self._hdr
        hdr[2] = _RAMWR
        self._cs(0)
        self._spi.write(hdr)

    def reset(self):
        if self._en is not None:
            self._en(1)
            time.sleep_ms(50)
        self._rst(1)
        time.sleep_ms(20)
        self._rst(0)
        time.sleep_ms(300)
        self._rst(1)
        time.sleep_ms(200)

    def _run_init(self):
        for cmd, data, delay in _INIT:
            self._cmd(cmd, data)
            if delay:
                time.sleep_ms(delay)

    # --- geometry -----------------------------------------------------------
    def rotation(self, value=None):
        if value is None:
            return self._rot
        self._rot = value & 3
        madctl, landscape = _ROTATIONS[self._rot]
        if landscape:
            self.width, self.height = NATIVE_HEIGHT, NATIVE_WIDTH
        else:
            self.width, self.height = NATIVE_WIDTH, NATIVE_HEIGHT
        self._cmd(_MADCTL, bytes((madctl,)))
        self._rowbuf = None
        return self._rot

    def _window(self, x0, y0, x1, y1):
        self._cmd(_CASET, bytes((x0 >> 8, x0 & 0xFF, x1 >> 8, x1 & 0xFF)))
        self._cmd(_RASET, bytes((y0 >> 8, y0 & 0xFF, y1 >> 8, y1 & 0xFF)))

    # --- drawing ------------------------------------------------------------
    def blit(self, x, y, w, h, buf):
        """Push a big-endian RGB565 buffer of w*h pixels at (x, y)."""
        if w <= 0 or h <= 0:
            return
        self._window(x, y, x + w - 1, y + h - 1)
        self._begin_pixels()
        self._spi.write(buf)
        self._cs(1)

    def fill_rect(self, x, y, w, h, color):
        if w <= 0 or h <= 0:
            return
        if self._rowbuf is None or len(self._rowbuf) < w * 2:
            self._rowbuf = bytearray(self.width * 2)
        row = memoryview(self._rowbuf)[: w * 2]
        lo = color & 0xFF
        hi = (color >> 8) & 0xFF
        for i in range(0, w * 2, 2):
            row[i] = lo
            row[i + 1] = hi
        self._window(x, y, x + w - 1, y + h - 1)
        self._begin_pixels()
        for _ in range(h):
            self._spi.write(row)
        self._cs(1)

    def fill(self, color=0):
        self.fill_rect(0, 0, self.width, self.height, color)

    # --- panel control ------------------------------------------------------
    def brightness(self, value=None):
        if value is None:
            return self._bl
        self._bl = max(0, min(255, int(value)))
        self._cmd(_WRDISBV, bytes((self._bl,)))
        return self._bl

    def invert(self, on=True):
        self._cmd(_INVON if on else _INVOFF)

    def tearing(self, on=True):
        self._cmd(_TEON, b"\x00") if on else self._cmd(_TEOFF)

    def on(self):
        self._cmd(_DISPON)
        self._cmd(_SLPOUT)
        time.sleep_ms(20)
        self.brightness(self._bl)

    def off(self):
        self._cmd(_DISPOFF)

    def sleep(self):
        self._cmd(_SLPIN)

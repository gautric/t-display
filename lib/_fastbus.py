"""Viper-accelerated 8-bit parallel writer for the ESP32-S3 GPIO block.

Imported inside a try/except by st7789p8: if the firmware was built without the
viper emitter this module fails to compile and the caller falls back to a plain
mem32 loop (same behaviour, roughly 15x slower).

ESP32-S3 GPIO registers:
    0x60004008 GPIO_OUT_W1TS   (pins 0-31 set)
    0x6000400C GPIO_OUT_W1TC   (pins 0-31 clear)
    0x60004014 GPIO_OUT1_W1TS  (pins 32-48 set)
    0x60004018 GPIO_OUT1_W1TC  (pins 32-48 clear)
"""

import micropython


@micropython.viper
def blast(buf: ptr8, n: int, tbl: ptr32, mask_all: int, wr_mask: int):
    """Clock n bytes of buf onto the bus, one WR pulse per byte.

    tbl maps a byte value to the GPIO_OUT1 bit pattern for the 8 data lines.
    """
    ts1 = ptr32(0x60004014)
    tc1 = ptr32(0x60004018)
    ts0 = ptr32(0x60004008)
    tc0 = ptr32(0x6000400C)
    i = 0
    while i < n:
        s = int(tbl[int(buf[i])])
        tc1[0] = mask_all ^ s
        ts1[0] = s
        tc0[0] = wr_mask
        ts0[0] = wr_mask
        i += 1


@micropython.viper
def blast_repeat(buf: ptr8, n: int, times: int, tbl: ptr32, mask_all: int,
                 wr_mask: int):
    """Clock buf[0:n] onto the bus `times` times (used for solid fills)."""
    ts1 = ptr32(0x60004014)
    tc1 = ptr32(0x60004018)
    ts0 = ptr32(0x60004008)
    tc0 = ptr32(0x6000400C)
    r = 0
    while r < times:
        i = 0
        while i < n:
            s = int(tbl[int(buf[i])])
            tc1[0] = mask_all ^ s
            ts1[0] = s
            tc0[0] = wr_mask
            ts0[0] = wr_mask
            i += 1
        r += 1

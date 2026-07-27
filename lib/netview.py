"""Network view: the public address of the board, and where it lands.

The counterpart of tradeview.TradeView. It owns the same vertical band between
the header and the footer, is handed the dict from ipinfo.fetch() and draws:

    big public ip        7-segment digits when the address is numeric,
                         scaled text otherwise (IPv6, or a hostname)
    city, region         with the ISO country code aligned right
    latitude, longitude   marked with a pin, green because it is a fix ipinfo
                         inferred from the address block, not a GPS reading
    org, timezone        the network announcing the address, and its zone

Geometry is derived from the panel height, so the same code fits the 536x240
AMOLED and the 320x170 LCD. Coordinates are screen-absolute; the Painter handed
to draw() applies the band offset.
"""

import gfx
import ipinfo

# Characters gfx.seg_text() has a glyph for. An IPv4 address is made of nothing
# else; an IPv6 address or a hostname is not, and falls back to scaled text.
_SEG_CHARS = "0123456789.- "

_NO_IP = "---.---.---.---"


class NetView:
    def __init__(self, width, height, pad=None):
        self.w = width
        self.h = height

        k = height / 240.0
        self.k = k
        self.wide = width >= 400

        self.pad = pad if pad is not None else max(6, int(10 * k))
        self.s_body = 2 if self.wide else 1
        self.s_alt = 3 if self.wide else 2  # non-numeric address fallback

        self.y_big = int(46 * k)
        self.h_big = int(50 * k)
        self.y_place = int(108 * k)
        self.y_coords = int(136 * k)
        self.y_org = int(170 * k)
        self.y_zone = int(190 * k)

    # ------------------------------------------------------------- address --
    def _address(self, p, info):
        """The public IP as the headline number, mirroring the rate readout."""
        pad = self.pad
        room = self.w - 2 * pad
        ip = (info or {}).get("ip") or ""
        p.text("public ip" if ip else "waiting for ipinfo.io", pad,
               self.y_big - int(11 * self.k), gfx.GREY, 1)

        text = ip or _NO_IP
        if _seg_ready(text) and gfx.seg_width(text, self.h_big) <= room:
            p.seg(text, pad, self.y_big, self.h_big,
                  gfx.CYAN if ip else gfx.DARK, gfx.GHOST)
            return
        # IPv6 or a hostname: shrink until it fits rather than run off the edge
        scale = self.s_alt
        while scale > 1 and gfx.text_width(text, scale) > room:
            scale -= 1
        p.text(gfx.clip_text(text, room // (8 * scale)), pad,
               self.y_big + (self.h_big - 8 * scale) // 2, gfx.CYAN, scale)

    # --------------------------------------------------------------- place --
    def _place(self, p, info):
        pad = self.pad
        s = self.s_body
        y = self.y_place
        room = self.w - 2 * pad
        country = (info or {}).get("country") or ""
        if country:
            width = gfx.text_width(country, s)
            p.text(country, self.w - pad - width, y, gfx.AMBER, s)
            room -= width + int(10 * self.k)
        place = ipinfo.format_place(info)
        p.text(gfx.clip_text(place or "unknown city", room // (8 * s)), pad, y,
               gfx.WHITE if place else gfx.GREY, s)

    # -------------------------------------------------------------- coords --
    def _coords(self, p, info):
        pad = self.pad
        y = self.y_coords
        text = ipinfo.format_coords(info)
        if not text:
            p.text("no coordinates", pad, y, gfx.GREY, 1)
            return
        size = max(3, int(5 * self.k))
        p.pin(pad, y, size, gfx.RED)
        p.text(text, pad + 3 * size, y, gfx.GREEN, self.s_body)

    # --------------------------------------------------------------- extra --
    def _extra(self, p, info):
        pad = self.pad
        limit = (self.w - 2 * pad) // 8
        org = (info or {}).get("org") or ""
        zone = (info or {}).get("timezone") or ""
        if org:
            p.text(gfx.clip_text(org, limit), pad, self.y_org, gfx.GREY, 1)
        if zone:
            p.text(gfx.clip_text(zone, limit), pad, self.y_zone, gfx.GREY, 1)

    # ----------------------------------------------------------------- api --
    def draw(self, p, info):
        self._address(p, info)
        self._place(p, info)
        self._coords(p, info)
        self._extra(p, info)


def _seg_ready(text):
    """True when gfx.seg_text() has a glyph for every character."""
    for ch in text:
        if ch not in _SEG_CHARS:
            return False
    return True

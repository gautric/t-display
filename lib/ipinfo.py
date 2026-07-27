"""Public IP address and coarse geo-location from ipinfo.io.

The board already knows its LAN address (wifi.ip()). What it cannot work out on
its own is the address the internet sees it as, and roughly where that address
sits:

    https://ipinfo.io/json

One unauthenticated GET returns a flat JSON object - ip, city, region, country,
loc ("lat,lon"), org, postal, timezone - a couple of hundred bytes, well inside
httpget's 32 kB cap. The coordinates are inferred from the address block, so
they are a city-level guess and not a GPS fix; treat them as such in the UI.

ipinfo.io throttles anonymous callers, which is why the view polls on its own
slow interval (config.NETINFO_SECONDS) instead of the quote refresh.

The fetcher is injected (get_json) so this module can be exercised off-device,
exactly like fx.
"""

import time

import log

_TAG = "ipinfo"

URL = "https://ipinfo.io/json"

# Copied straight through. Anything ipinfo omits for a given address comes back
# as "" rather than None, so the view never has to test for a missing key.
_FIELDS = ("ip", "hostname", "city", "region", "country", "org", "postal",
           "timezone")


def _text(data, key):
    value = data.get(key)
    return "" if value is None else str(value).strip()


def _coords(loc):
    """'48.8566,2.3522' -> (48.8566, 2.3522). (None, None) when unusable."""
    if not loc or "," not in loc:
        return None, None
    lat, _, lon = loc.partition(",")
    try:
        return float(lat), float(lon)
    except ValueError:
        log.warn(_TAG, "cannot parse loc %r", loc)
        return None, None


def _result(data):
    """Normalise a reply into the fixed shape the network view expects."""
    info = {}
    for key in _FIELDS:
        info[key] = _text(data, key)
    lat, lon = _coords(_text(data, "loc"))
    info["lat"] = lat
    info["lon"] = lon
    info["source"] = "ipinfo.io"
    return info


def fetch(get_json, url=None):
    """Return a location dict for this board's public address.

    Raises OSError on any transport or parse problem, so the refresh loop can
    treat it like every other fetch.
    """
    t0 = time.ticks_ms()
    try:
        data = get_json(url or URL)
    except Exception as exc:  # noqa: BLE001 - any transport/parse issue
        log.warn(_TAG, "lookup failed: %r", exc)
        raise OSError("ipinfo lookup failed: %r" % exc)
    if not isinstance(data, dict) or not _text(data, "ip"):
        raise OSError("no ip in the ipinfo.io reply")
    info = _result(data)
    log.info(_TAG, "%s at %s, %s in %d ms", info["ip"],
             format_place(info) or "an unknown place",
             format_coords(info) or "no coordinates", log.since(t0))
    return info


# ------------------------------------------------------------- formatting ----
def format_place(info):
    """'Paris, Ile-de-France', or whichever of the two ipinfo knew."""
    if not info:
        return ""
    parts = [part for part in (info.get("city"), info.get("region")) if part]
    return ", ".join(parts)


def _degrees(value, places, positive, negative):
    if value is None:
        return ""
    return (("%." + str(places) + "f %s")
            % (abs(value), positive if value >= 0 else negative))


def format_lat(info, places=4):
    """'48.8566 N', empty when ipinfo returned no coordinates."""
    return _degrees((info or {}).get("lat"), places, "N", "S")


def format_lon(info, places=4):
    """'2.3522 E', empty when ipinfo returned no coordinates."""
    return _degrees((info or {}).get("lon"), places, "E", "W")


def format_coords(info, places=4):
    """Both halves on one line, empty unless ipinfo gave a usable loc."""
    lat = format_lat(info, places)
    lon = format_lon(info, places)
    if not lat or not lon:
        return ""
    return "%s  %s" % (lat, lon)

"""EUR/JPY (or any pair) quotes from public, key-free endpoints.

Primary source is Frankfurter, which serves the ECB reference rates and can
return the latest quote plus a date range in a single request, so one call feeds
both the big number and the sparkline.
    https://api.frankfurter.dev/v1/2026-06-12..?base=EUR&symbols=JPY
Fallback is open.er-api.com, used only when Frankfurter is unreachable.

The fetcher is injected (get_json) so this module can be exercised off-device.
"""

import time

import log

_TAG = "fx"

FRANKFURTER = "https://api.frankfurter.dev/v1"
ERAPI = "https://open.er-api.com/v6/latest/%s"

# MicroPython's epoch is 2000-01-01, CPython's is 1970-01-01. Either way a
# freshly booted board reports a year below this, which means "clock not set".
_MIN_SANE_YEAR = 2023


def _iso_date(epoch):
    tm = time.localtime(epoch)
    return "%04d-%02d-%02d" % (tm[0], tm[1], tm[2])


def clock_is_set(now=None):
    if now is None:
        now = time.time()
    return time.localtime(now)[0] >= _MIN_SANE_YEAR


def _result(rate, date, series=None, dates=None, source=""):
    prev = series[-2] if series and len(series) > 1 else None
    change = None
    change_pct = None
    if prev:
        change = rate - prev
        change_pct = change * 100.0 / prev
    return {
        "rate": rate,
        "inverse": (1.0 / rate) if rate else None,
        "date": date,
        "prev": prev,
        "change": change,
        "change_pct": change_pct,
        "series": series or [rate],
        "dates": dates or ([date] if date else []),
        "source": source,
    }


def _timeseries(get_json, base, quote, days, now):
    start = _iso_date(now - days * 86400)
    url = "%s/%s..?base=%s&symbols=%s" % (FRANKFURTER, start, base, quote)
    data = get_json(url)
    rates = data.get("rates") or {}
    dates = sorted(rates.keys())
    series = []
    kept = []
    for day in dates:
        value = rates[day].get(quote)
        if value is not None:
            series.append(float(value))
            kept.append(day)
    if not series:
        raise ValueError("empty series for %s%s" % (base, quote))
    log.debug(_TAG, "history %s..%s, %d points, %s..%s", kept[0], kept[-1],
              len(series), series[0], series[-1])
    return _result(series[-1], kept[-1], series, kept, "ECB")


def _latest(get_json, base, quote):
    url = "%s/latest?base=%s&symbols=%s" % (FRANKFURTER, base, quote)
    data = get_json(url)
    rate = float(data["rates"][quote])
    return _result(rate, data.get("date", ""), None, None, "ECB")


def _erapi(get_json, base, quote):
    data = get_json(ERAPI % base, limit=65536)
    rate = float(data["rates"][quote])
    date = (data.get("time_last_update_utc") or "")[5:16]
    return _result(rate, date, None, None, "er-api")


def fetch(get_json, base="EUR", quote="JPY", days=45, now=None):
    """Return a quote dict. Tries history, then latest, then the fallback API."""
    if now is None:
        now = time.time()
    errors = []
    t0 = time.ticks_ms()
    if clock_is_set(now):
        try:
            result = _timeseries(get_json, base, quote, days, now)
            log.info(_TAG, "%s%s %s (%s) via history in %d ms", base, quote,
                     format_rate(result["rate"]), result["date"],
                     log.since(t0))
            return result
        except Exception as exc:  # noqa: BLE001 - any transport/parse issue
            errors.append(exc)
            log.warn(_TAG, "history unavailable: %r", exc)
    else:
        log.debug(_TAG, "clock not set, skipping the dated request")
    for name, provider in (("latest", _latest), ("er-api", _erapi)):
        try:
            result = provider(get_json, base, quote)
            log.info(_TAG, "%s%s %s (%s) via %s in %d ms", base, quote,
                     format_rate(result["rate"]), result["date"],
                     result["source"], log.since(t0))
            return result
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)
            log.warn(_TAG, "%s failed: %r", name, exc)
    log.error(_TAG, "all providers failed after %d ms", log.since(t0))
    raise OSError("fx fetch failed: %s" % "; ".join(repr(e) for e in errors))


# ------------------------------------------------------------- formatting ----
def decimals_for(value):
    """Number of decimals that suits the magnitude at hand."""
    av = abs(value or 0.0)
    if av >= 100:
        return 2
    if av >= 10:
        return 3
    if av >= 1:
        return 4
    return 6


def format_rate(value, places=None):
    if value is None:
        return "---"
    if places is None:
        places = decimals_for(value)
    return ("%." + str(places) + "f") % value


def format_change(quote):
    """e.g. '+0.15 (+0.08%)', scaled to the precision of the rate itself."""
    change = quote.get("change")
    if change is None:
        return ""
    pct = quote.get("change_pct") or 0.0
    places = decimals_for(quote.get("rate") or change)
    sign = "+" if change >= 0 else "-"
    return "%s%s (%s%.2f%%)" % (sign, format_rate(abs(change), places), sign,
                                abs(pct))

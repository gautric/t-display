"""Dashboard configuration.

Everything that is not a secret lives here. Wi-Fi credentials come from
secrets.py (git-ignored) so they never end up in version control.
"""

try:
    from secrets import WIFI_SSID, WIFI_PASSWORD
except ImportError:  # board flashed without secrets.py
    WIFI_SSID = ""
    WIFI_PASSWORD = ""

# ---------------------------------------------------------------- board -----
# "amoled" -> LilyGO T-Display-S3 AMOLED, RM67162, 536x240 (default)
# "lcd"    -> LilyGO T-Display-S3,       ST7789,  170x320 8-bit parallel
BOARD = "amoled"

# 0/2 = portrait, 1/3 = landscape
ROTATION = 1

# 0..255. AMOLED drives the panel register, LCD dims the backlight with PWM.
BRIGHTNESS = 0xD0

# RM67162 is routed through the GPIO matrix, so 40 MHz is the safe ceiling.
SPI_BAUDRATE = 40_000_000

# Height in pixels of the reusable render band. The screen is painted band by
# band so we never allocate a full frame buffer (536*240*2 = 251 kB).
# 48 rows on the AMOLED is ~50 kB.
BAND_HEIGHT = 48

# --------------------------------------------------------------- network ----
WIFI_HOSTNAME = "t-display-fx"
WIFI_TIMEOUT = 25  # seconds
NTP_HOST = "pool.ntp.org"
TZ_OFFSET = 2 * 3600  # displayed clock offset from UTC (Europe/Paris summer)

# ------------------------------------------------------------------- fx -----
# Displayed as BASE/QUOTE, e.g. EUR/JPY = "1 EUR costs N JPY".
BASE = "EUR"
QUOTE = "USD"

# Pair menu. The left button (refresh) fetches the next entry, so a press on
# EUR/USD moves the dashboard to EUR/JPY. Boot starts on BASE/QUOTE when it is
# listed here, otherwise on the first entry. One entry = plain refresh, no menu.
PAIRS = (
    ("EUR", "USD"),
    ("EUR", "JPY"),
)

HISTORY_DAYS = 45  # window requested for the sparkline
# ECB publishes once a day around 16:00 CET, so half an hour between fetches
# still catches the new rate quickly while keeping the API traffic low.
REFRESH_SECONDS = 300
RETRY_SECONDS = 30  # after a failed fetch
TICK_SECONDS = 5  # screen repaint interval (clock / countdown)

# --------------------------------------------------------------- netinfo ----
# One extra menu entry after the pairs, showing the public IP address of the
# board plus the city, country and coordinates ipinfo.io infers from it. False
# keeps the menu pairs-only and leaves netview/ipinfo unimported.
SHOW_NETINFO = True
IPINFO_URL = "https://ipinfo.io/json"

# ipinfo.io throttles anonymous callers, and the answer only changes when the
# ISP hands out a new address, so this view polls far slower than the quote.
NETINFO_SECONDS = 900

# --------------------------------------------------------------- logging ----
# DEBUG / INFO / WARN / ERROR / OFF. `make debug` forces DEBUG without editing
# this file. DEBUG adds per-request and per-frame timings plus heap usage.
LOG_LEVEL = "INFO"

# --------------------------------------------------------------- runtime ----
USE_WATCHDOG = False
WATCHDOG_TIMEOUT = 120  # seconds, only used when USE_WATCHDOG is True

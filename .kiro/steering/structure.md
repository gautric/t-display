# Repository structure

```
t-display/
├── Makefile              host tooling: venv, firmware, upload, deploy, logs
├── main.py               entry point, boot sequence and refresh loop
├── config.py             all non-secret configuration (committed)
├── secrets.py            WIFI_SSID / WIFI_PASSWORD (git-ignored)
├── secrets.example.py    template to copy into secrets.py
├── lib/                  everything uploaded to /lib on the device
│   ├── _fastbus.py       @micropython.viper GPIO blast for the parallel bus
│   ├── fx.py             rate fetching, formatting, change/percent maths
│   ├── gfx.py            colours, scaled text, 7-segment, sparkline, icons
│   ├── httpget.py        minimal HTTP/1.0 + TLS client (no urequests)
│   ├── log.py            levelled logger with uptime prefix and heap reporting
│   ├── rm67162.py        AMOLED driver, 536x240, QSPI
│   ├── screen.py         banded framebuffer renderer + display factory
│   ├── st7789p8.py       LCD driver, 170x320, 8-bit parallel
│   ├── tradeview.py      the rate/change/inverse/sparkline panel
│   ├── ui.py             Dashboard: header, footer, clock, splash, layout
│   └── wifi.py           station management, IP/RSSI, NTP sync
├── firmware/             downloaded .bin files (git-ignored)
└── .venv/                host-side mpremote + esptool (git-ignored)
```

`main.py`, `config.py` and `secrets.py` land at the device filesystem root;
`lib/*.py` lands in `/lib`, which is already on MicroPython's `sys.path`. That is
why modules import each other flat (`import gfx`, not `from lib import gfx`).

## Layering

```
main.py
  ├── config, log, wifi, httpget, fx        state + data
  └── screen.Screen / make_display / buttons
        └── ui.Dashboard
              └── tradeview.TradeView
                    └── gfx
        └── rm67162.RM67162  |  st7789p8.ST7789P8 (lazy import)
                                    └── _fastbus (optional viper fast path)
```

Rules that keep this layering honest:

- **Drivers know nothing about the app.** They only take pixel buffers.
- **UI code never touches a driver.** It draws through the `Painter` passed to it.
- **`fx.fetch` takes the fetcher as an argument** (`fx.fetch(httpget.get_json, ...)`)
  so quote logic can be exercised without a network or a board.
- **Only `main.py` reads `config`** for runtime behaviour; `screen.make_display`
  and `screen.buttons` receive the config module and use `getattr` with defaults.

## The rendering model

`Screen` allocates one horizontal band (`config.BAND_HEIGHT` rows, ~50 kB on the
AMOLED) and calls the draw callback once per band with a `Painter` whose `dy`
offset shifts every y coordinate. `framebuf` clips whatever falls outside the
band, so **UI code always draws in screen-absolute coordinates** and never thinks
about bands.

Consequences to respect when editing UI code:

- The draw callback is invoked several times per frame. Keep it pure — no I/O, no
  allocation, no mutation of state.
- Anything expensive (network, string building from live data) belongs in the
  fetch path in `main.py`, not in `draw`.

## Application state

`main.py` owns a single `state` dict and passes it down:

```python
{"quote": ..., "error": ..., "ip": ..., "rssi": ...,
 "refresh_fraction": 0.0, "base": "EUR", "quote_ccy": "USD"}
```

`quote` is the dict returned by `fx.fetch`:
`rate, inverse, date, prev, change, change_pct, series, dates, source`.
When the pair changes, `quote` and `error` are cleared so the numbers can never
disagree with the header.

## Configuration split

- `config.py` — board, rotation, brightness, SPI baudrate, band height, Wi-Fi
  hostname/timeout, NTP host, timezone offset, pair menu, history window,
  refresh/retry/tick intervals, log level, watchdog. Committed.
- `secrets.py` — Wi-Fi credentials only. Git-ignored. `config.py` imports it
  inside a `try/except ImportError` so a board flashed without it still boots.

Never move a credential into `config.py`, and never read `secrets` outside
`config.py`.

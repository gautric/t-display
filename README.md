# t-display-fx

An FX rate dashboard for the **LilyGO T-Display-S3**, running **MicroPython** on
stock `ESP32_GENERIC_S3` firmware. The board joins Wi-Fi, pulls European Central
Bank reference rates over HTTPS, and paints a live dashboard on the built-in
panel.

```
[   0.549] I main: esp32 1.28.0 on Generic ESP32S3 module with Octal-SPIRAM with ESP32S3
[   1.491] I screen: amoled panel 536x240 ready in 932 ms
[   1.836] I wifi: clock set from pool.ntp.org in 24 ms
[   2.460] I fx: EURUSD 1.1389 (2026-07-27) via history in 449 ms
[   2.468] I main: EUR/USD = 1.1389 USD, +0.0012 (+0.11%), 32 history points
```

No third-party MicroPython packages are installed on the device. HTTP, the
display drivers and the drawing primitives are all implemented in `lib/`.

## What it shows

The FX view, one per pair in `config.PAIRS`:

- the current rate as large 7-segment digits (`BASE/QUOTE`, so `EUR/JPY` reads
  "1 EUR costs N JPY")
- absolute and percentage change against the previous published rate, coloured
  and marked with an up/down triangle
- the inverse rate
- a sparkline over the last `HISTORY_DAYS`
- a header with the pair name and menu dots, a footer with the clock, Wi-Fi
  signal bars, LAN IP and error/status text
- a hairline countdown to the next refresh

The network view (`SHOW_NETINFO = True`) shows the public IP address of the
board plus the city, country and coordinates that ipinfo.io infers from it.

## Hardware

| Button | GPIO | Action |
| --- | --- | --- |
| Left (BOOT) | 0 | Refresh now and advance to the next menu entry |
| Right | 21 (amoled) / 14 (lcd) | Cycle brightness through `BRIGHTNESS_STEPS` |

The left button walks every pair in `config.PAIRS` and then the network view,
e.g. `EUR/USD -> EUR/JPY -> NETWORK -> EUR/USD`.

Two panels are supported, selected with `config.BOARD`:

- `"amoled"` (default) — T-Display-S3 AMOLED 1.91", RM67162, 536x240, QSPI
- `"lcd"` — T-Display-S3, ST7789, 170x320, 8-bit i8080 parallel bus

Both drivers expose the same surface (`width`, `height`, `rotation()`, `blit`,
`fill`, `brightness`), so nothing above the driver layer knows which panel is
attached.

## Quick start

Host requirements: macOS, Python 3, GNU Make. `mpremote` and `esptool` are
installed into a project-local `.venv` on demand — Homebrew Python refuses
global pip installs (PEP 668), so the venv is not optional.

```sh
cp secrets.example.py secrets.py   # then fill in WIFI_SSID / WIFI_PASSWORD
make devices                       # confirm the board is seen
make firmware                      # download the newest SPIRAM_OCT build
make erase flash                   # one-time: write MicroPython
make deploy                        # upload the project and reboot
make monitor                       # watch the log
```

Run `make` with no arguments for the full target list plus the detected port,
board and log level.

Port detection picks the first `/dev/cu.usbmodem*`, `/dev/cu.wchusbserial*` or
`/dev/cu.SLAB_USBtoUART*`. Override it on any target with `PORT=/dev/cu.xxx`.

## Commands

| Target | What it does |
| --- | --- |
| `make devices` | List serial ports mpremote can see |
| `make check` | Host-side syntax check (`compileall`). Cheap — run it often |
| `make upload` | Copy `main.py`, `config.py`, `secrets.py`, `lib/` to the board |
| `make deploy` | `upload` + `reset` |
| `make run` | Run the *host* copy of `main.py` on the board, streaming output |
| `make repl` | Interactive REPL (Ctrl-] to exit) |
| `make monitor` | Attach to the log of whatever is already running |
| `make monitor-boot` | Soft-reset first, so the log starts at the boot banner |
| `make debug` | Run with `LOG_LEVEL` forced to `DEBUG` (timings + heap) |
| `make logs` | Same as `run`, pipe-friendly: `make logs \| tee run.log` |
| `make df` | Free flash and free heap on the device |
| `make ls` | List the device filesystem |
| `make test` | On-device smoke test: Wi-Fi + NTP + one `fx.fetch` |
| `make set-level LEVEL=DEBUG` | Rewrite `LOG_LEVEL` in `config.py` |
| `make wipe` | Remove only the files this project installs |
| `make clean` | Drop `__pycache__` |

**Always run `make check` after editing Python.** It catches syntax errors before
they reach flash.

There is no unit test suite. `make test` is an on-device smoke check, not an
assertion suite. Anything touching drivers, timing or memory can only be
validated on hardware.

## Firmware

The board runs the stock `ESP32_GENERIC_S3` build, `SPIRAM_OCT` variant, from
[micropython.org](https://micropython.org/download/ESP32_GENERIC_S3/). The
T-Display-S3 carries an ESP32-S3 with 8 MB of *octal* PSRAM, so the plain
variant would leave most of the heap unused. A correctly flashed board reports:

```
uname: (sysname='esp32', release='1.28.0',
        machine='Generic ESP32S3 module with Octal-SPIRAM with ESP32S3')
flash free 14328 kB
heap free 8125 kB
```

`make firmware` scrapes the download page for the newest dated release build,
saves it under `firmware/` and points `firmware/latest.bin` at it. Preview
builds are deliberately not matched.

### Updating

```sh
make firmware                       # fetch the newest release
make erase flash                    # write it
make deploy                         # put the project back
```

`make erase` runs `esptool erase_flash`, which **destroys the device
filesystem**. Everything this project installs is restored by `make deploy`, but
anything you only ever edited on the board is gone for good. Check
`make ls` against the repo first and pull down anything that is not tracked:

```sh
.venv/bin/mpremote connect $(make port) fs cp :lib/thing.py ./thing.py
```

Skipping the erase (`make flash` alone) usually preserves the filesystem, since
the image is written at offset 0 and the VFS partition sits beyond the app. It
is the faster path for a minor version bump; the full erase is the safer one
across several releases, where the partition layout may have moved.

### Two things that will trip you up

**esptool often cannot put the board into download mode by itself.** The failure
looks like this:

```
A fatal error occurred: Failed to connect to ESP32-S3: No serial data received.
```

While MicroPython is still running, ask the board to do it from the inside:

```sh
.venv/bin/mpremote connect /dev/cu.usbmodemXXXX bootloader
```

Otherwise hold **BOOT** while tapping **RESET**. Either way the USB device
re-enumerates, so wait a few seconds and re-detect the port before running
esptool. Calls issued too early fail with a stale handle — `termios error (6,
'Device not configured')` or `could not enter raw repl`. Retry, do not debug.

**The port name changes with the firmware.** In download mode the chip appears
as the ROM USB-Serial/JTAG unit (`303a:1001`), on a different `/dev/cu.usbmodem*`
node than the running application. Pass `PORT=` explicitly to `make erase` and
`make flash`:

```sh
make erase flash PORT=/dev/cu.usbmodem2101
```

After a successful flash, give the board 5-10 seconds before expecting the REPL
to answer.

## Configuration

`config.py` holds everything that is not a secret and is committed.
`secrets.py` holds Wi-Fi credentials only and is git-ignored; `config.py`
imports it inside a `try/except ImportError` so a board flashed without it still
boots. Never move a credential into `config.py`, and never read `secrets`
anywhere but `config.py`.

| Knob | Default | Notes |
| --- | --- | --- |
| `BOARD` | `"amoled"` | `"amoled"` or `"lcd"` |
| `ROTATION` | `1` | 0/2 portrait, 1/3 landscape |
| `BRIGHTNESS` | `0xD0` | Panel register on AMOLED, PWM backlight on LCD |
| `SPI_BAUDRATE` | 40 MHz | RM67162 goes through the GPIO matrix; 40 MHz is the safe ceiling |
| `BAND_HEIGHT` | `48` | Rows per render band; 48 on the AMOLED is ~50 kB |
| `WIFI_HOSTNAME` | `"t-display-fx"` | DHCP hostname |
| `WIFI_TIMEOUT` | `25` | seconds |
| `NTP_HOST` | `pool.ntp.org` | Best-effort; the UI copes with an unset clock |
| `TZ_OFFSET` | `2 * 3600` | Displayed clock offset from UTC |
| `BASE` / `QUOTE` | `EUR` / `USD` | Boot pair, if `PAIRS` lists it |
| `PAIRS` | EUR/USD, EUR/JPY | The menu the left button walks |
| `HISTORY_DAYS` | `45` | Sparkline window |
| `REFRESH_SECONDS` | `300` | Quote refresh interval |
| `RETRY_SECONDS` | `30` | After a failed fetch |
| `TICK_SECONDS` | `5` | Repaint interval for the clock and countdown |
| `SHOW_NETINFO` | `True` | Adds the network view to the menu |
| `NETINFO_SECONDS` | `900` | ipinfo.io throttles anonymous callers |
| `LOG_LEVEL` | `"INFO"` | `DEBUG` / `INFO` / `WARN` / `ERROR` / `OFF` |
| `USE_WATCHDOG` | `False` | `WATCHDOG_TIMEOUT` seconds when enabled |

## Data sources

`lib/fx.py` tries, in order, and reports the winner as `source` in the quote:

1. **Frankfurter timeseries** — `https://api.frankfurter.dev/v1/<start>..?base=&symbols=`
   returns the latest rate and the whole history window in one request, so a
   single call feeds both the big number and the sparkline. Reported as `ECB`.
2. **Frankfurter latest** — same host, no history. Also `ECB`.
3. **`https://open.er-api.com/v6/latest/<base>`** — last resort, reported as
   `er-api`.

Step 1 is skipped when the clock is not set, because it needs a start date.
`fx.fetch` takes the fetcher as an argument (`fx.fetch(httpget.get_json, ...)`),
so the quote logic can be exercised without a network or a board. `fx` must not
import `httpget`.

`lib/ipinfo.py` backs the network view via `https://ipinfo.io/json`.

## Layout

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
│   ├── ipinfo.py         public IP address and coarse geo-location
│   ├── log.py            levelled logger with uptime prefix and heap reporting
│   ├── netui.py          NetDashboard: the network view
│   ├── netview.py        the public-address / location panel
│   ├── rm67162.py        AMOLED driver, 536x240, QSPI
│   ├── screen.py         banded framebuffer renderer + display factory
│   ├── st7789p8.py       LCD driver, 170x320, 8-bit parallel
│   ├── tradeui.py        TradeDashboard: the FX view
│   ├── tradeview.py      the rate/change/inverse/sparkline panel
│   ├── ui.py             Chrome: header, footer, clock, splash, layout
│   └── wifi.py           station management, IP/RSSI, NTP sync
├── firmware/             downloaded .bin files (git-ignored)
└── .venv/                host-side mpremote + esptool (git-ignored)
```

`main.py`, `config.py` and `secrets.py` land at the device filesystem root;
`lib/*.py` lands in `/lib`, which is already on MicroPython's `sys.path`. That
is why modules import each other flat (`import gfx`, not `from lib import gfx`).

### Layering

```
main.py
  ├── config, log, wifi, httpget, fx, ipinfo    state + data
  └── screen.Screen / make_display / buttons
        └── ui.Chrome
              ├── tradeui.TradeDashboard -> tradeview -> gfx
              └── netui.NetDashboard     -> netview   -> gfx
        └── rm67162.RM67162 | st7789p8.ST7789P8 (lazy import)
                                    └── _fastbus (optional viper fast path)
```

Rules that keep this honest:

- **Drivers know nothing about the app.** They only take pixel buffers.
- **UI code never touches a driver.** It draws through the `Painter` it is given.
- **Only `main.py` reads `config`** for runtime behaviour. Library code takes the
  config module as an argument and uses `getattr` with defaults, so an older
  `config.py` on a board still boots.

### The rendering model

A full 536x240 RGB565 frame is 251 kB, more than the heap can spare. So `Screen`
allocates one horizontal band (`config.BAND_HEIGHT` rows, ~50 kB on the AMOLED)
and calls the draw callback once per band with a `Painter` whose `dy` offset
shifts every y coordinate. `framebuf` clips whatever falls outside the band, so
**UI code always draws in screen-absolute coordinates** and never thinks about
bands.

Two consequences when editing UI code:

- The draw callback runs several times per frame. Keep it pure — no I/O, no
  allocation, no mutation of state.
- Anything expensive (network, string building from live data) belongs in the
  fetch path in `main.py`.

### Application state

`main.py` owns a single `state` dict and passes it down:

```python
{"quote": ..., "net": ..., "error": ..., "ip": ..., "rssi": ...,
 "refresh_fraction": 0.0, "base": "EUR", "quote_ccy": "USD", "view": ...}
```

`quote` is what `fx.fetch` returns: `rate`, `inverse`, `date`, `prev`, `change`,
`change_pct`, `series`, `dates`, `source`. When the pair changes, `quote` and
`error` are cleared so the numbers can never disagree with the header.

## Logging

`lib/log.py` prints `[   3.412] I wifi: joined ...` to the USB serial console.
Levels are `DEBUG` 10, `INFO` 20, `WARN` 30, `ERROR` 40, `OFF` 100.

Each module defines a module-level `TAG` / `_TAG` and passes it first. Use lazy
formatting — `log.debug(TAG, "cycle %d, %s", cycle, pair)`, never a pre-formatted
string. `log.since(t0)` gives elapsed milliseconds, `log.mem(TAG, note)` reports
heap usage, and `log.exception(TAG, exc, msg, *args)` belongs in `except` blocks.

Per-request and per-frame timings live at `DEBUG`. Keep it that way; `INFO`
should stay readable on a live board.

## Networking

`wifi.connect(...)` runs at boot and `wifi.ensure(...)` before each fetch, so a
dropped link reconnects. Power save is disabled (`PM_NONE`) because it wrecks
latency on this board.

`wifi.sync_time(NTP_HOST)` is best-effort. When the clock is unset, `fx` skips
the dated request and the UI shows `--:--`; never assume `time.localtime()` is
valid.

`httpget.get` / `get_json` speak HTTP/1.0, follow up to 2 redirects, de-chunk
responses, cap the body at 32 kB and raise `OSError` on status >= 400. TLS goes
through `ssl.wrap_socket` with `CERT_NONE`: **certificates are not verified.**
That is a deliberate tradeoff for a device with no cert store and no RTC, and it
is why nothing sensitive travels over these connections.

## Design priorities

1. **Fit in the heap.** Rendering is banded and buffers are reused. Never
   allocate a full-screen framebuffer.
2. **Stay up unattended.** Fetch failures fall back to `RETRY_SECONDS`, the clock
   and countdown keep ticking offline, and an optional watchdog is available.
   A broad `except Exception` in the fetch path is correct here — the dashboard
   must not die because one API misbehaved.
3. **No external MicroPython packages.** Everything runs on stock firmware.

## Contributing

Match the existing code; it is deliberately uniform. PEP 8, 4-space indent, a
79-column limit, `%`-style formatting rather than f-strings, no type hints
outside viper pointer annotations, and a docstring on every module explaining
the hardware or protocol rationale. See `.kiro/steering/conventions.md` for the
full set, including how to add a panel driver, a UI element, a config knob or a
data source.

Do not commit `secrets.py`, `firmware/`, `.venv/` or `__pycache__` — all are
ignored.

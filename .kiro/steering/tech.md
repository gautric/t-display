# Technology and workflow

## Stack

| Layer | What | Notes |
| --- | --- | --- |
| Language | MicroPython (Python 3 subset) | No CPython-only stdlib |
| Firmware | `ESP32_GENERIC_S3`, `SPIRAM_OCT` variant | Stock build from micropython.org |
| MCU | ESP32-S3 | `machine`, `network`, `framebuf`, `ntptime`, `ssl` |
| Host tooling | `mpremote` 1.28.0, `esptool` 5.3.1 | Pinned in the Makefile, installed into `.venv` |
| Build system | GNU Make | macOS-oriented (BSD `sed`, `/dev/cu.*` ports) |

There is no `requirements.txt`; host dependencies are pinned inline in the
Makefile's `$(MPREMOTE)` rule. The venv is project-local because Homebrew Python
refuses global pip installs (PEP 668). Any device target bootstraps it on demand.

No third-party MicroPython libraries are installed on the device. `urequests` is
deliberately absent — `lib/httpget.py` implements what is needed.

## Commands

Run `make` (or `make help`) to see the list plus the detected port, board and log
level. Common ones:

```sh
make devices        # list serial ports mpremote can see
make check          # host-side syntax check (compileall) - cheap, run this often
make deploy         # upload main.py, config.py, secrets.py, lib/ then reset
make upload         # copy files only, no reset
make run            # run the host copy of main.py on the board, streaming output
make repl           # interactive REPL (Ctrl-] to exit)
make monitor        # attach to the log of whatever is already running
make monitor-boot   # soft-reset first, so the log starts at the boot banner
make debug          # run with LOG_LEVEL forced to DEBUG (timings + heap)
make logs           # same as run, pipe-friendly: make logs | tee run.log
make df             # free flash and free heap on the device
make ls             # list the device filesystem
make test           # on-device smoke test: Wi-Fi + NTP + one fx.fetch
make clean          # drop __pycache__
```

One-time board setup:

```sh
make firmware       # scrape + download the newest ESP32_GENERIC_S3-SPIRAM_OCT build
make erase flash    # write it (hold BOOT if the board will not enter download mode)
```

Port detection picks the first `/dev/cu.usbmodem*`, `/dev/cu.wchusbserial*` or
`/dev/cu.SLAB_USBtoUART*`. Override with `PORT=/dev/cu.xxx` on any target.

`make set-level LEVEL=DEBUG` rewrites `LOG_LEVEL` in `config.py` for the copy that
ships to the board; `make debug` forces the level at runtime without editing the
file.

## Verification expectations

- **Always run `make check` after editing Python.** It is a pure host-side
  `compileall` and catches syntax errors before they reach flash.
- There is no unit test suite and no test framework. `make test` is an on-device
  smoke check, not an assertion suite. Do not add a test framework unless asked.
- Anything touching drivers, timing or memory can only be validated on hardware.
  When you cannot run on a board, say so instead of implying it was verified.
- `make df` and `log.mem(...)` are the tools for checking a change did not blow the
  heap budget.

## Logging

`lib/log.py` prints `[   3.412] I wifi: joined ...` to the USB serial console.
Levels: `DEBUG` 10, `INFO` 20, `WARN` 30, `ERROR` 40, `OFF` 100.

- Each module defines a module-level `TAG` / `_TAG` string and passes it first.
- Use lazy formatting: `log.debug(TAG, "cycle %d, %s", cycle, pair)` — never
  pre-format the string.
- `log.since(t0)` for elapsed milliseconds, `log.mem(TAG, note)` for heap usage,
  `log.exception(TAG, exc, msg, *args)` in `except` blocks.
- `DEBUG` is where per-request and per-frame timings live. Keep it that way; INFO
  should stay readable on a live board.

## Networking

- `wifi.connect(ssid, password, timeout, hostname)` at boot;
  `wifi.ensure(...)` before each fetch so a dropped link reconnects.
- Power save is disabled (`PM_NONE`) because it wrecks latency on this board.
- `wifi.sync_time(NTP_HOST)` is best-effort. When the clock is unset, `fx` skips
  history and the UI shows `--:--`; never assume `time.localtime()` is valid.
- `httpget.get`/`get_json` speak HTTP/1.0, follow up to 2 redirects, de-chunk
  responses, cap the body at 32 kB and raise `OSError` on status >= 400. TLS goes
  through `ssl.wrap_socket` with `CERT_NONE` — certificates are not verified,
  which is a deliberate tradeoff for a device with no cert store and no RTC.

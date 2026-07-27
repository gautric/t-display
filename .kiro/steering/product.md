# Product

An FX (currency) rate dashboard that runs on a **LilyGO T-Display-S3** board under
**MicroPython**. It joins Wi-Fi, pulls European Central Bank reference rates over
HTTPS, and paints a live dashboard on the built-in display.

## What it shows

- The current rate as large 7-segment digits (`BASE/QUOTE`, e.g. `EUR/JPY` reads
  "1 EUR costs N JPY")
- Absolute and percentage change vs. the previous published rate, coloured and
  marked with an up/down triangle
- The inverse rate
- A sparkline of the last `HISTORY_DAYS` of history
- Header with the pair name and menu dots, footer with clock, Wi-Fi signal bars,
  IP address and error/status text
- A hairline countdown to the next refresh

## Hardware controls

| Button | GPIO | Action |
| --- | --- | --- |
| Left (BOOT) | 0 | Refresh now and advance to the next pair in `config.PAIRS` |
| Right | 21 (amoled) / 14 (lcd) | Cycle brightness through `BRIGHTNESS_STEPS` |

## Supported boards

Selected with `config.BOARD`:

- `"amoled"` (default) — T-Display-S3 AMOLED 1.91", RM67162 controller, 536x240,
  QSPI
- `"lcd"` — T-Display-S3, ST7789 controller, 170x320, 8-bit i8080 parallel bus

Both drivers expose the same surface (`width`, `height`, `blit`, `fill`,
`brightness`, `rotation`), so nothing above the driver layer knows which panel is
attached.

## Data sources

`lib/fx.py` tries, in order:

1. Frankfurter timeseries — `https://api.frankfurter.dev/v1` (rate + history)
2. Frankfurter latest — same host, no history
3. `https://open.er-api.com/v6/latest/<base>` — last-resort fallback

The chosen source is reported in the quote dict as `source` and shown in the UI.

## Design priorities

1. **Fit in the heap.** The board has limited RAM; a full 536x240 RGB565 frame is
   251 kB. Rendering is banded and buffers are reused.
2. **Stay up unattended.** Fetch failures fall back to `RETRY_SECONDS`, the clock
   and countdown keep ticking offline, and an optional watchdog is available.
3. **No external MicroPython packages.** Everything runs on stock
   `ESP32_GENERIC_S3` firmware; HTTP is implemented locally in `lib/httpget.py`.

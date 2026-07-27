# Coding conventions

Match the existing code. It is deliberately uniform.

## Style

- PEP 8, 4-space indent, **79-column limit** (the whole repo respects it).
- `snake_case` functions and variables, `CapWords` classes, `_leading_underscore`
  for module-private helpers and `_UPPER` for module-private constants.
- **No type hints.** The only annotations in the repo are viper pointer types
  (`buf: ptr8`, `tbl: ptr32`) where the emitter requires them.
- **`%`-style formatting, no f-strings.** Cheaper and consistent with the logger.
- Module docstring on every file, explaining the hardware or protocol rationale,
  not just the name. Docstring on every public function and class.
- Section banners to break up long modules:
  `# --- low level ---------------------------------------------------------`
  or `# ----------------------------------------------------------- board -----`.
- Comments explain *why* (a register quirk, a memory limit, a panel offset), not
  what the next line does.

## MicroPython-specific patterns

- `from micropython import const` for register addresses, bit masks and opcodes.
  `const()` is compile-time and produces no runtime lookup.
- Precompute lookup tables into `array("I", ...)` rather than recomputing per
  pixel (see the 256-entry byte→GPIO table in `st7789p8.py`).
- Reuse buffers. Allocate `bytearray` once, slice with `memoryview` — never build
  a new buffer inside a render loop.
- `__slots__` on small hot classes (`Painter`).
- `time.ticks_ms()` / `ticks_add` / `ticks_diff` for all timing. Never subtract
  raw tick values, they wrap.
- Explicit `gc.collect()` at cycle boundaries, followed by `log.mem(...)`.
- Lazy imports for anything large or board-specific (drivers are imported inside
  `make_display`, `machine.WDT` inside the `USE_WATCHDOG` branch).
- Optional native fast paths go behind `try/except ImportError` with a working
  pure-Python fallback and a module-level flag (`st7789p8.FAST`). The app must
  still run on firmware without the viper emitter, just slower.
- Broad `except Exception` is acceptable around optional firmware features and in
  the fetch path — the dashboard must not die because one API misbehaved. Log it
  with `log.exception` and carry on.

## Adding things

**A new panel driver:** implement the same surface as `RM67162` / `ST7789P8`
(`width`, `height`, `rotation()`, `blit(x, y, w, h, buf)`, `fill`, `brightness`),
register it in `screen.make_display`, and add its button pair to
`screen.buttons`. Nothing else should need to change.

**A new UI element:** add the primitive to `gfx.py`, expose it on `Painter` in
`screen.py` with the `dy` offset applied, then use it from `ui.py` or
`tradeview.py`. Scale geometry from `k = height / 240.0` so it survives both
panels, and branch on `wide = width >= 400` when a layout only fits the AMOLED.
Colours come from `gfx` constants, produced by `gfx.rgb()` which byte-swaps for
`framebuf` — never hardcode a raw RGB565 literal.

**A new config knob:** add it to `config.py` with a comment giving units and the
reason for the default. Read it in `main.py`, or via `getattr(cfg, "NAME",
default)` in library code so an older `config.py` on a board still boots.

**A new data source:** add a fetch helper in `fx.py` and slot it into the
fallback chain in `fx.fetch`, returning through `_result(...)` so the quote dict
keeps its shape. Keep the fetcher injected — `fx` must not import `httpget`.

## Things to avoid

- Adding a third-party MicroPython dependency.
- Allocating a full-screen framebuffer.
- Doing I/O or allocation inside a `render` callback.
- Putting credentials anywhere but `secrets.py`.
- Committing `secrets.py`, `firmware/`, `.venv/` or `__pycache__` (all ignored).

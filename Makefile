# EUR/JPY dashboard - LilyGO T-Display S3 / MicroPython
#
#   make tools          create .venv with mpremote + esptool (done automatically)
#   make devices        list serial ports MicroPython can see
#   make firmware       download the latest ESP32_GENERIC_S3 firmware
#   make erase flash    write that firmware to the board (one time)
#   make upload         copy main.py, config.py, secrets.py and lib/ to the board
#   make reset          reboot the board so main.py runs
#   make deploy         upload + reset
#   make run            run main.py from the host without installing it
#   make repl           open the REPL (Ctrl-] to exit)
#   make monitor        watch the log of the program already running on the board
#   make monitor-boot   soft-reset, then watch the log from the boot banner
#   make logs           stream the log of the host copy of main.py (pipe-friendly)
#   make debug          same as logs with LEVEL=DEBUG forced (timings, heap)
#   make set-level LEVEL=DEBUG   change LOG_LEVEL in config.py

# Host tools live in a project-local venv: macOS/homebrew Python refuses
# global pip installs (PEP 668). Any device target bootstraps it on demand.
PY       ?= python3
VENV     ?= .venv
MPREMOTE ?= $(VENV)/bin/mpremote
ESPTOOL  ?= $(VENV)/bin/esptool
BAUD     ?= 460800
CHIP     ?= esp32s3
VARIANT  ?= SPIRAM_OCT
LEVEL    ?= DEBUG
FW_DIR   ?= firmware
FW       ?= $(FW_DIR)/latest.bin

# First USB serial port that looks like an ESP32-S3 on macOS.
PORT ?= $(shell ls /dev/cu.usbmodem* /dev/cu.wchusbserial* /dev/cu.SLAB_USBtoUART* 2>/dev/null | head -n1)
DEV  := $(if $(PORT),connect $(PORT),)

ROOT_FILES := main.py config.py secrets.py
LIB_FILES  := $(wildcard lib/*.py)

.DEFAULT_GOAL := help
.PHONY: help tools devices port check upload deploy reset run repl monitor \
        monitor-boot logs debug set-level ls df firmware flash erase wipe \
        test clean distclean

help:
	@sed -n 's/^#   //p' $(MAKEFILE_LIST)
	@echo ""
	@echo "port     : $(if $(PORT),$(PORT),NOT FOUND - plug the board in or pass PORT=/dev/cu.xxx)"
	@echo "board    : $(shell sed -n 's/^BOARD = //p' config.py)"
	@echo "log level: $(shell sed -n 's/^LOG_LEVEL = //p' config.py) installed, $(LEVEL) for 'make debug'"

tools: $(MPREMOTE)

$(MPREMOTE):
	$(PY) -m venv $(VENV)
	$(VENV)/bin/pip install --quiet --upgrade pip
	$(VENV)/bin/pip install --quiet 'mpremote==1.28.0' 'esptool==5.3.1'
	@$(MPREMOTE) version

$(ESPTOOL): $(MPREMOTE)
	@test -x $(ESPTOOL) || { echo "esptool missing from $(VENV)"; exit 1; }

devices: $(MPREMOTE)
	$(MPREMOTE) devs

port:
	@echo $(PORT)

# Syntax-check every file on the host before pushing it to flash.
check:
	@$(PY) -m compileall -q main.py config.py secrets.py lib >/dev/null && echo "syntax ok"

upload: check $(MPREMOTE)
	@test -f secrets.py || { echo "secrets.py missing: cp secrets.example.py secrets.py"; exit 1; }
	@test -n "$(PORT)" || { echo "no serial port found, pass PORT=/dev/cu.xxx"; exit 1; }
	-$(MPREMOTE) $(DEV) fs mkdir :lib
	$(MPREMOTE) $(DEV) fs cp $(LIB_FILES) :lib/
	$(MPREMOTE) $(DEV) fs cp $(ROOT_FILES) :
	@echo "uploaded to $(PORT)"

deploy: upload reset

reset: $(MPREMOTE)
	$(MPREMOTE) $(DEV) reset

run: $(MPREMOTE)
	$(MPREMOTE) $(DEV) run main.py

repl: $(MPREMOTE)
	$(MPREMOTE) $(DEV) repl

# Attach to the board and watch the log of whatever is already running.
# Needs a real terminal (Ctrl-] quits, Ctrl-C stops the program).
monitor: $(MPREMOTE)
	@echo "attaching to $(PORT) - Ctrl-] to detach, Ctrl-C to stop the program"
	$(MPREMOTE) $(DEV) repl

# Soft-reset first, so the log starts at the boot banner.
monitor-boot: $(MPREMOTE)
	@echo "soft-reset + attach to $(PORT) - Ctrl-] to detach"
	$(MPREMOTE) $(DEV) soft-reset repl

# Stream the log of the host copy of main.py, e.g. `make logs | tee run.log`.
logs: $(MPREMOTE)
	$(MPREMOTE) $(DEV) run main.py

# Same, with the log level forced (LEVEL=DEBUG by default, no config edit).
debug: $(MPREMOTE)
	$(MPREMOTE) $(DEV) exec "import log; log.set_level('$(LEVEL)')" run main.py

# Flip the level the installed copy boots with, then push it.
set-level:
	@sed -i '' 's/^LOG_LEVEL = .*/LOG_LEVEL = "$(LEVEL)"/' config.py
	@grep -n '^LOG_LEVEL' config.py

ls: $(MPREMOTE)
	$(MPREMOTE) $(DEV) fs ls :
	-$(MPREMOTE) $(DEV) fs ls :lib

df: $(MPREMOTE)
	$(MPREMOTE) $(DEV) exec "import os,gc;s=os.statvfs('/');print('flash free %d kB'%(s[0]*s[3]//1024));gc.collect();print('heap free %d kB'%(gc.mem_free()//1024))"

# Fetch the quote on-device and print it, useful to check Wi-Fi + TLS alone.
test: $(MPREMOTE)
	$(MPREMOTE) $(DEV) exec "import config,wifi,httpget,fx;wifi.connect(config.WIFI_SSID,config.WIFI_PASSWORD);print(wifi.ip(),wifi.rssi());wifi.sync_time(config.NTP_HOST);q=fx.fetch(httpget.get_json,config.BASE,config.QUOTE,config.HISTORY_DAYS);print(q['source'],q['date'],q['rate'],fx.format_change(q))"

firmware:
	@mkdir -p $(FW_DIR)
	@url=$$(curl -fsSL https://micropython.org/download/ESP32_GENERIC_S3/ \
		| grep -o '/resources/firmware/ESP32_GENERIC_S3-$(VARIANT)-[0-9]\{8\}-v[0-9.]*\.bin' \
		| sort -u | tail -n1); \
	test -n "$$url" || { echo "could not find a $(VARIANT) build on micropython.org"; exit 1; }; \
	echo "downloading https://micropython.org$$url"; \
	curl -fL -o "$(FW_DIR)/$$(basename $$url)" "https://micropython.org$$url"; \
	ln -sf "$$(basename $$url)" $(FW)
	@ls -l $(FW_DIR)

erase: $(ESPTOOL)
	@test -n "$(PORT)" || { echo "no serial port found, pass PORT=/dev/cu.xxx"; exit 1; }
	$(ESPTOOL) --chip $(CHIP) --port $(PORT) erase_flash

flash: $(ESPTOOL)
	@test -f $(FW) || { echo "$(FW) missing, run: make firmware"; exit 1; }
	@test -n "$(PORT)" || { echo "no serial port found, pass PORT=/dev/cu.xxx"; exit 1; }
	$(ESPTOOL) --chip $(CHIP) --port $(PORT) --baud $(BAUD) write_flash 0 $(FW)

# Remove only the files this project installs.
wipe: $(MPREMOTE)
	-$(MPREMOTE) $(DEV) exec "import os;[os.remove('/lib/'+f) for f in os.listdir('/lib')];os.rmdir('/lib')"
	-$(MPREMOTE) $(DEV) exec "import os;[os.remove(f) for f in ('main.py','config.py','secrets.py') if f in os.listdir('/')]"

clean:
	rm -rf __pycache__ lib/__pycache__

distclean: clean
	rm -rf $(VENV)

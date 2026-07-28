"""The two clock screens: shared chrome around the clockview panels.

Counterpart of tradeui and netui, holding both dashboards because they differ
only in which panel they build. Neither reads the RTC itself: the epoch is
sampled once per frame by main.py and travels in the state dict, so every band
of a frame agrees on the second.
"""

from clockview import AnalogView, DigitalView, local
from ui import View


class _ClockDashboard(View):
    """Common wiring: local time in, one panel out."""

    def __init__(self, chrome, seconds=True):
        super().__init__(chrome)
        self.tz = chrome.tz
        self.seconds = seconds
        self.face = None  # set by the subclass

    def data(self, state):
        return state.get("clock")

    def panel(self, p, data, state):
        self.face.draw(p, local(state.get("now"), self.tz), data)


class AnalogDashboard(_ClockDashboard):
    """Round dial with hour, minute and second hands."""

    def __init__(self, chrome, seconds=True):
        super().__init__(chrome, seconds)
        self.face = AnalogView(chrome.w, chrome.h, chrome.pad, chrome.tz,
                               seconds)

    def title(self):
        return "ANALOG"


class DigitalDashboard(_ClockDashboard):
    """Big 7-segment HH:MM with the seconds and the date."""

    def __init__(self, chrome, seconds=True):
        super().__init__(chrome, seconds)
        self.face = DigitalView(chrome.w, chrome.h, chrome.pad, chrome.tz,
                                seconds)

    def title(self):
        return "DIGITAL"

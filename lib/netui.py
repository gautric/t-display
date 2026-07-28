"""The network screen: shared chrome around netview.NetView.

Counterpart of tradeui. It reads the ipinfo lookup out of the state dict and
hands it to the panel; nothing here knows how the lookup was made or how the
address is laid out.
"""

from netview import NetView
from ui import View

_TITLE = "NETWORK"


class NetDashboard(View):
    """Public address, city, country and coordinates from ipinfo.io."""

    def __init__(self, chrome):
        super().__init__(chrome)
        self.net = NetView(chrome.w, chrome.h, chrome.pad)

    # ----------------------------------------------------------------- api --
    def title(self):
        return _TITLE

    def data(self, state):
        return state.get("net")

    def panel(self, p, data, state):
        self.net.draw(p, data)

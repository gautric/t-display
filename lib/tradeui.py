"""The currency-pair screen: shared chrome around tradeview.TradeView.

Thin on purpose. It owns which pair is on show and where the numbers come from
in the state dict; the layout of the readout itself belongs to TradeView and
the frame around it to ui.Chrome.
"""

from tradeview import TradeView
from ui import View


class TradeDashboard(View):
    """The default view: one pair, its change, its inverse, its history."""

    def __init__(self, chrome, base="EUR", quote="JPY"):
        super().__init__(chrome)
        self.base = base
        self.quote = quote
        self.trade = TradeView(chrome.w, chrome.h, base, quote, chrome.pad)

    def set_pair(self, base, quote):
        """Point the view at another pair from the menu."""
        self.base = base
        self.quote = quote
        self.trade.set_pair(base, quote)

    def pair(self):
        return "%s/%s" % (self.base, self.quote)

    # ----------------------------------------------------------------- api --
    def title(self):
        return self.pair()

    def data(self, state):
        return state.get("quote")

    def panel(self, p, data, state):
        self.trade.draw(p, data)

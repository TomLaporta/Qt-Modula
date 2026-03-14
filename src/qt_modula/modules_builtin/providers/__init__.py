"""Provider-backed network module family."""

from qt_modula.modules_builtin.providers.fx_quote import FxQuoteModule
from qt_modula.modules_builtin.providers.http_request import HttpRequestModule
from qt_modula.modules_builtin.providers.market_fetcher import MarketFetcherModule

__all__ = ["FxQuoteModule", "HttpRequestModule", "MarketFetcherModule"]

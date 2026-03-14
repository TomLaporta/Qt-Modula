"""Service abstractions and implementations."""

from qt_modula.services.errors import ServiceError, ServiceErrorKind
from qt_modula.services.export import (
    ExportRequest,
    ExportResult,
    ExportWriter,
    TextExportRequest,
    TextExportResult,
    TextExportWriter,
    text_writer_for_format,
    writer_for_format,
)
from qt_modula.services.http import (
    DefaultHttpClient,
    HttpClient,
    HttpRequest,
    HttpResponse,
)
from qt_modula.services.providers import (
    FxProvider,
    FxQuote,
    FxQuoteRequest,
    MarketHistory,
    MarketHistoryProfile,
    MarketHistoryProfileRequest,
    MarketHistoryProvider,
    MarketHistoryRequest,
    YFinanceFxProvider,
    YFinanceMarketHistoryProvider,
)
from qt_modula.services.results import (
    ServiceFailure,
    ServiceResult,
    ServiceSuccess,
    capture_service_result,
    service_failure,
    service_success,
)
from qt_modula.services.settings_state import (
    configure_export_root,
    configure_from_app_config,
    configure_provider_network,
    current_export_root,
    current_provider_network,
)

__all__ = [
    "DefaultHttpClient",
    "ExportRequest",
    "ExportResult",
    "ExportWriter",
    "FxProvider",
    "FxQuote",
    "FxQuoteRequest",
    "HttpClient",
    "HttpRequest",
    "HttpResponse",
    "MarketHistory",
    "MarketHistoryProfile",
    "MarketHistoryProfileRequest",
    "MarketHistoryProvider",
    "MarketHistoryRequest",
    "ServiceError",
    "ServiceErrorKind",
    "ServiceFailure",
    "ServiceResult",
    "ServiceSuccess",
    "TextExportRequest",
    "TextExportResult",
    "TextExportWriter",
    "YFinanceFxProvider",
    "YFinanceMarketHistoryProvider",
    "capture_service_result",
    "configure_export_root",
    "configure_from_app_config",
    "configure_provider_network",
    "current_export_root",
    "current_provider_network",
    "service_failure",
    "service_success",
    "text_writer_for_format",
    "writer_for_format",
]

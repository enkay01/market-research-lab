"""Domain route modules for Market Research Lab."""

from __future__ import annotations

from .backtests import router as backtests_router
from .cleanup import router as cleanup_router
from .deps import ErrorResponse, register_domain_exception_handlers
from .indicators import router as indicators_router
from .market_data import router as market_data_router
from .options import router as options_router
from .projects import router as projects_router
from .strategies import router as strategies_router

__all__ = [
    "ErrorResponse",
    "backtests_router",
    "cleanup_router",
    "indicators_router",
    "market_data_router",
    "options_router",
    "projects_router",
    "register_domain_exception_handlers",
    "strategies_router",
]


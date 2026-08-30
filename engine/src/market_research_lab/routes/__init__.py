"""Domain route modules for Market Research Lab."""

from __future__ import annotations

from .alerts import router as alerts_router
from .backtests import router as backtests_router
from .cleanup import router as cleanup_router
from .indicators import router as indicators_router
from .market_data import router as market_data_router
from .options import router as options_router
from .predictive_models import router as predictive_models_router
from .projects import router as projects_router
from .strategies import router as strategies_router
from .valuations import router as valuations_router

__all__ = [
    "alerts_router",
    "backtests_router",
    "cleanup_router",
    "indicators_router",
    "market_data_router",
    "options_router",
    "predictive_models_router",
    "projects_router",
    "strategies_router",
    "valuations_router",
]

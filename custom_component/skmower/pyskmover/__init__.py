"""
pyskmover - Python library for SK-Robot lawn mower communication.

Implements the REST API protocol observed in sk-mover-komunikacja.log.
Provides a thread-safe client with automatic reconnection, periodic state
polling and command/status APIs.
"""

from .client import SkMowerClient
from .models import (
    DeviceStatus,
    DeviceSetting,
    DeviceSchedule,
    WorkMode,
)
from .exceptions import (
    SkMowerError,
    SkMowerAuthError,
    SkMowerConnectionError,
    SkMowerApiError,
)

__all__ = [
    "SkMowerClient",
    "DeviceStatus",
    "DeviceSetting",
    "DeviceSchedule",
    "WorkMode",
    "SkMowerError",
    "SkMowerAuthError",
    "SkMowerConnectionError",
    "SkMowerApiError",
]

__version__ = "1.0.0"
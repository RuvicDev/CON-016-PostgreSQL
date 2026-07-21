"""Conector Ruvic de solo lectura para PostgreSQL."""

from .client import PostgresqlClient
from .config import ENV_PREFIX, PostgresqlConfig
from .exceptions import (
    PostgresqlAuthError,
    PostgresqlConnectorError,
    PostgresqlDataError,
    PostgresqlNetworkError,
)
from .logging_utils import setup_logging

__all__ = [
    "ENV_PREFIX",
    "PostgresqlAuthError",
    "PostgresqlClient",
    "PostgresqlConfig",
    "PostgresqlConnectorError",
    "PostgresqlDataError",
    "PostgresqlNetworkError",
    "setup_logging",
]

__version__ = "1.0.0"

"""Excepciones propias del conector PostgreSQL.

Separan los tres tipos de fallo que el usuario debe distinguir:
autenticación, red/servidor y datos. Nunca exponemos excepciones
crípticas del driver subyacente.
"""


class PostgresqlConnectorError(Exception):
    """Error base del conector."""


class PostgresqlAuthError(PostgresqlConnectorError):
    """Credenciales inválidas o permisos insuficientes."""


class PostgresqlNetworkError(PostgresqlConnectorError):
    """No se pudo alcanzar el servidor (host/puerto/red/timeout)."""


class PostgresqlDataError(PostgresqlConnectorError):
    """La operación es válida pero el objeto no existe o el query es inválido."""

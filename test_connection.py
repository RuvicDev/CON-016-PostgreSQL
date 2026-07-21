"""Prueba de conexión estándar del conector postgresql.

Firma estándar Ruvic: def test_connection() -> tuple[bool, str]
- Lee la configuración EXCLUSIVAMENTE de las env vars RUVIC_POSTGRESQL_*.
- Nunca lanza excepciones; retorna (ok, mensaje).

Ejecutable también como script para pruebas locales:
    python test_connection.py
"""

from __future__ import annotations


def test_connection() -> tuple[bool, str]:
    """Conecta a PostgreSQL y ejecuta SELECT 1 usando las env vars RUVIC_POSTGRESQL_*."""
    try:
        from ruvic_postgresql_connector import (
            PostgresqlAuthError,
            PostgresqlClient,
            PostgresqlDataError,
            PostgresqlNetworkError,
        )
    except ImportError:
        return (
            False,
            "La librería ruvic-postgresql-connector no está instalada. "
            "Instala con: pip install git+https://github.com/Dgirto/"
            "PostgreSQL.git#subdirectory=lib",
        )

    try:
        client = PostgresqlClient()  # valida que existan las env vars
    except ValueError as exc:
        return False, str(exc)

    try:
        client.ping()
    except PostgresqlAuthError as exc:
        return False, f"Autenticación fallida: {exc}"
    except PostgresqlNetworkError as exc:
        return False, f"Error de red: {exc}"
    except PostgresqlDataError as exc:
        return False, f"Error de datos: {exc}"
    except Exception as exc:  # red de seguridad: jamás propagar
        return False, f"Error inesperado: {exc}"

    return (
        True,
        f"Conexión exitosa a {client.config.host}:{client.config.port}/"
        f"{client.config.database}",
    )


if __name__ == "__main__":
    ok, message = test_connection()
    print(f"{'OK' if ok else 'FALLO'}: {message}")
    raise SystemExit(0 if ok else 1)

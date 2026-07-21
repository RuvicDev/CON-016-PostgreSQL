"""Cliente de solo lectura para PostgreSQL.

Capacidades:
- list_tables():      listar tablas de un esquema.
- read_table():       leer filas de una tabla con límite.
- table_stats():      estadísticas de una tabla (filas, tamaño, columnas).
- explain_query():    plan de ejecución de un query SIN ejecutarlo.

Las credenciales SIEMPRE provienen de variables de entorno RUVIC_POSTGRESQL_*
(ver config.PostgresqlConfig.from_env). Prohibido hardcodearlas.
"""

from __future__ import annotations

import re
from typing import Any

import psycopg
from psycopg.rows import dict_row

from .config import PostgresqlConfig
from .exceptions import (
    PostgresqlAuthError,
    PostgresqlConnectorError,
    PostgresqlDataError,
    PostgresqlNetworkError,
)
from .logging_utils import get_logger

_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

# Códigos SQLSTATE relevantes (ver Apéndice A de la documentación de PostgreSQL).
_AUTH_SQLSTATES = {"28P01", "28000"}  # invalid_password, invalid_authorization_specification
_PERMISSION_SQLSTATES = {"42501"}  # insufficient_privilege
_MISSING_DB_SQLSTATES = {"3D000"}  # invalid_catalog_name
_MISSING_TABLE_SQLSTATES = {"42P01"}  # undefined_table


def _wrap_query_error(exc: psycopg.Error, not_found_message: str) -> PostgresqlConnectorError:
    """Traduce un error del driver ocurrido durante una consulta a una
    excepción propia, sin dejar escapar nunca el tipo crudo del driver."""
    sqlstate = getattr(exc, "sqlstate", None)
    if sqlstate in _PERMISSION_SQLSTATES:
        return PostgresqlAuthError(
            "El usuario no tiene permiso SELECT sobre ese esquema o tabla. "
            "Revisa el GRANT en el servidor."
        )
    if sqlstate in _MISSING_TABLE_SQLSTATES:
        return PostgresqlDataError(not_found_message)
    return PostgresqlDataError(f"Error de datos: {exc}")


def _human_size(num_bytes: int | None) -> str:
    """Convierte bytes a un tamaño legible (ej. "12 MB")."""
    if not num_bytes:
        return "0 B"
    size = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            return f"{size:.1f} {unit}" if unit != "B" else f"{int(size)} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


def _validate_identifier(name: str, kind: str) -> None:
    """Valida nombres de tabla/esquema para evitar inyección SQL."""
    if not _IDENTIFIER_RE.match(name):
        raise PostgresqlDataError(
            f"Nombre de {kind} inválido: {name!r}. "
            "Solo se permiten letras, números y guion bajo."
        )


class PostgresqlClient:
    """Cliente de solo lectura para PostgreSQL.

    Args:
        config: configuración de conexión. Si se omite, se lee de las
            variables de entorno RUVIC_POSTGRESQL_* (comportamiento estándar
            en el runtime de la plataforma).

    Ejemplo:
        >>> client = PostgresqlClient()     # lee RUVIC_POSTGRESQL_* del entorno
        >>> client.list_tables()
        [{'schema': 'public', 'table': 'clientes', 'rows_estimate': 1520}]
    """

    def __init__(self, config: PostgresqlConfig | None = None) -> None:
        self.config = config or PostgresqlConfig.from_env()
        self._logger = get_logger()

    # ------------------------------------------------------------------ #
    # Conexión
    # ------------------------------------------------------------------ #

    def _connect(self) -> psycopg.Connection:
        try:
            conn = psycopg.connect(
                host=self.config.host,
                port=self.config.port,
                dbname=self.config.database,
                user=self.config.username,
                password=self.config.password,
                connect_timeout=self.config.connect_timeout,
                options="-c default_transaction_read_only=on",
                row_factory=dict_row,
            )
        except psycopg.OperationalError as exc:
            sqlstate = getattr(exc, "sqlstate", None)
            if sqlstate in _AUTH_SQLSTATES:
                raise PostgresqlAuthError(
                    "Autenticación fallida: usuario o contraseña inválidos, "
                    "o el usuario no tiene acceso a la base de datos."
                ) from exc
            if sqlstate in _MISSING_DB_SQLSTATES:
                raise PostgresqlDataError(
                    f"La base de datos {self.config.database!r} no existe."
                ) from exc
            raise PostgresqlNetworkError(
                f"No se pudo conectar a {self.config.host}:{self.config.port} "
                f"(timeout {self.config.connect_timeout}s). Verifica host, puerto "
                "y acceso de red."
            ) from exc
        return conn

    def ping(self) -> bool:
        """Verifica la conexión ejecutando SELECT 1.

        Returns:
            True si la conexión funciona.

        Raises:
            PostgresqlAuthError / PostgresqlNetworkError / PostgresqlDataError según el fallo.
        """
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                cur.fetchone()
        finally:
            conn.close()
        self._logger.info("Ping exitoso a %s:%s", self.config.host, self.config.port)
        return True

    # ------------------------------------------------------------------ #
    # Capacidad 1: listar tablas
    # ------------------------------------------------------------------ #

    def list_tables(self, schema: str = "public") -> list[dict[str, Any]]:
        """Lista las tablas de un esquema con su conteo estimado de filas.

        Args:
            schema: esquema a inspeccionar (default "public").

        Returns:
            Lista de dicts: {"schema", "table", "rows_estimate"}.

        Ejemplo:
            >>> client.list_tables()
            [{'schema': 'public', 'table': 'ventas', 'rows_estimate': 89123}]
        """
        _validate_identifier(schema, "esquema")
        query = """
            SELECT schemaname AS schema_name,
                   relname    AS table_name,
                   n_live_tup AS rows_estimate
            FROM pg_stat_user_tables
            WHERE schemaname = %s
            ORDER BY relname
        """
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.execute(query, (schema,))
                rows = [
                    {
                        "schema": row["schema_name"],
                        "table": row["table_name"],
                        "rows_estimate": row["rows_estimate"],
                    }
                    for row in cur.fetchall()
                ]
        finally:
            conn.close()
        self._logger.info("Se listaron %d tablas del esquema %s", len(rows), schema)
        return rows

    # ------------------------------------------------------------------ #
    # Capacidad 2: leer una tabla
    # ------------------------------------------------------------------ #

    def read_table(
        self,
        table: str,
        schema: str = "public",
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Lee filas de una tabla como lista de diccionarios.

        Args:
            table: nombre de la tabla.
            schema: esquema (default "public").
            limit: máximo de filas a retornar (default 100, máximo 10000).

        Returns:
            Lista de dicts, una entrada por fila.

        Ejemplo:
            >>> client.read_table("clientes", limit=5)
            [{'id': 1, 'nombre': 'ACME', ...}, ...]
        """
        _validate_identifier(table, "tabla")
        _validate_identifier(schema, "esquema")
        limit = max(1, min(int(limit), 10_000))
        query = f'SELECT * FROM "{schema}"."{table}" LIMIT %s'
        not_found = f'La tabla "{schema}"."{table}" no existe.'
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                try:
                    cur.execute(query, (limit,))
                    rows = cur.fetchall()
                except psycopg.Error as exc:
                    conn.rollback()
                    raise _wrap_query_error(exc, not_found) from exc
        finally:
            conn.close()
        self._logger.info(
            'Leídas %d filas de "%s"."%s" (limit=%d)', len(rows), schema, table, limit
        )
        return rows

    # ------------------------------------------------------------------ #
    # Capacidad 3: estadísticas de una tabla
    # ------------------------------------------------------------------ #

    def table_stats(self, table: str, schema: str = "public") -> dict[str, Any]:
        """Obtiene estadísticas de una tabla.

        Args:
            table: nombre de la tabla.
            schema: esquema (default "public").

        Returns:
            Dict con: row_count (exacto), total_size (legible, ej. "12 MB"),
            y columns (lista de {"name", "type", "nullable"}).

        Ejemplo:
            >>> client.table_stats("ventas")
            {'row_count': 89123, 'total_size': '12.0 MB', 'columns': [...]}
        """
        _validate_identifier(table, "tabla")
        _validate_identifier(schema, "esquema")
        qualified = f'"{schema}"."{table}"'
        columns_query = """
            SELECT column_name AS name,
                   data_type   AS type,
                   is_nullable = 'YES' AS nullable
            FROM information_schema.columns
            WHERE table_schema = %s AND table_name = %s
            ORDER BY ordinal_position
        """
        not_found = f"La tabla {qualified} no existe."
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                try:
                    cur.execute(columns_query, (schema, table))
                    columns = [
                        {"name": row["name"], "type": row["type"], "nullable": row["nullable"]}
                        for row in cur.fetchall()
                    ]
                    if not columns:
                        raise PostgresqlDataError(not_found)

                    cur.execute(
                        "SELECT pg_total_relation_size(%s::regclass) AS total_size",
                        (qualified,),
                    )
                    total_size = cur.fetchone()["total_size"]

                    cur.execute(f"SELECT COUNT(*) AS row_count FROM {qualified}")
                    row_count = cur.fetchone()["row_count"]
                except psycopg.Error as exc:
                    conn.rollback()
                    raise _wrap_query_error(exc, not_found) from exc
        finally:
            conn.close()
        return {
            "schema": schema,
            "table": table,
            "row_count": row_count,
            "total_size": _human_size(total_size),
            "columns": columns,
        }

    # ------------------------------------------------------------------ #
    # Capacidad 4: EXPLAIN de un query (NUNCA lo ejecuta)
    # ------------------------------------------------------------------ #

    def explain_query(self, query: str) -> dict[str, Any]:
        """Describe el plan de ejecución de un query SIN ejecutarlo.

        Usa EXPLAIN (FORMAT JSON) sin ANALYZE — el planificador solo estima
        el plan, nunca ejecuta el query ni modifica datos.

        Args:
            query: consulta SQL a analizar (solo se permite un statement,
                y debe ser un SELECT).

        Returns:
            Dict con: total_cost estimado y el plan completo como árbol JSON.

        Ejemplo:
            >>> client.explain_query("SELECT * FROM ventas WHERE anio = 2026")
            {'total_cost': 1543.2, 'plan': {...}}
        """
        statement = query.strip().rstrip(";")
        if ";" in statement:
            raise PostgresqlDataError(
                "Solo se permite analizar un statement a la vez (sin ';')."
            )
        if not statement.lower().lstrip().startswith("select"):
            raise PostgresqlDataError(
                "explain_query solo acepta sentencias SELECT."
            )
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                try:
                    cur.execute(f"EXPLAIN (FORMAT JSON) {statement}")
                    (raw_plan,) = list(cur.fetchone().values())
                except psycopg.Error as exc:
                    conn.rollback()
                    raise PostgresqlDataError(
                        f"Query inválido, no se pudo planificar: {exc}"
                    ) from exc
        finally:
            conn.close()

        plan_root = raw_plan[0]["Plan"]
        return {
            "total_cost": plan_root.get("Total Cost"),
            "plan": plan_root,
        }

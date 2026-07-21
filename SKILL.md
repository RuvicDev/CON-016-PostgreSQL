---
name: postgresql
description: >
  Usa la librería ruvic_postgresql_connector para consultar bases de datos
  PostgreSQL en modo solo lectura - listar tablas (list_tables), leer datos
  (read_table), obtener estadísticas de tablas (table_stats) y analizar el
  plan de ejecución de un query sin ejecutarlo (explain_query). Úsala cuando
  el usuario pida consultar, explorar o analizar una base de datos
  PostgreSQL.
triggers:
- postgresql
- postgres
- base de datos
- consultar tabla
- explain
---

# Conector PostgreSQL (ruvic_postgresql_connector)

Librería Python de solo lectura para PostgreSQL. Está **preinstalada en el runtime** cuando el conector está configurado (si no, instálala con `pip install git+https://github.com/Dgirto/PostgreSQL.git#subdirectory=lib`).

## Regla crítica de credenciales

El código generado **NUNCA hardcodea credenciales**. Siempre se leen de variables de entorno, disponibles cuando el conector `postgresql` está configurado:

| Variable | Contenido |
|----------|-----------|
| `RUVIC_POSTGRESQL_HOST` | Host del servidor |
| `RUVIC_POSTGRESQL_PORT` | Puerto (default 5432) |
| `RUVIC_POSTGRESQL_DATABASE` | Nombre de la base de datos |
| `RUVIC_POSTGRESQL_USERNAME` | Usuario |
| `RUVIC_POSTGRESQL_PASSWORD` | Contraseña |
| `RUVIC_POSTGRESQL_CONNECT_TIMEOUT` | (opcional) timeout en segundos |

Si estas variables NO existen, el conector no está configurado: no generes código que lo use; indica al usuario que lo configure en **Settings → Conectores**.

## Conexión (siempre igual)

```python
from ruvic_postgresql_connector import PostgresqlClient

client = PostgresqlClient()  # lee RUVIC_POSTGRESQL_* del entorno automáticamente
```

## Capacidad 1 — Listar tablas

```python
tables = client.list_tables()          # esquema "public" por defecto
tables = client.list_tables("ventas")  # o un esquema específico
for t in tables:
    print(f"{t['schema']}.{t['table']}: ~{t['rows_estimate']} filas")
```

## Capacidad 2 — Leer una tabla

```python
rows = client.read_table("clientes", limit=50)
for row in rows:
    print(row)  # cada fila es un dict {columna: valor}
```

## Capacidad 3 — Estadísticas de una tabla

```python
stats = client.table_stats("ventas")
print(f"Filas: {stats['row_count']}, Tamaño: {stats['total_size']}")
for col in stats["columns"]:
    print(f"  {col['name']}: {col['type']} (nullable={col['nullable']})")
```

## Capacidad 4 — Plan de ejecución de un query (sin ejecutarlo)

```python
plan = client.explain_query("SELECT * FROM ventas WHERE anio = 2026")
print(f"Costo estimado: {plan['total_cost']}")
print(plan["plan"])  # árbol completo de EXPLAIN (FORMAT JSON)
```

`explain_query` usa `EXPLAIN (FORMAT JSON)` sin `ANALYZE`, y solo acepta sentencias `SELECT`: el query nunca se ejecuta ni modifica datos.

## Manejo de errores

```python
from ruvic_postgresql_connector import (
    PostgresqlAuthError, PostgresqlDataError, PostgresqlNetworkError,
)

try:
    rows = client.read_table("pedidos")
except PostgresqlAuthError:
    print("Credenciales inválidas — revisa la configuración del conector")
except PostgresqlNetworkError:
    print("No se pudo alcanzar el servidor — revisa host/puerto/red")
except PostgresqlDataError as e:
    print(f"Error de datos: {e}")  # ej. la tabla no existe
```

## Buenas prácticas al generar código

1. Lee credenciales SOLO de las variables `RUVIC_POSTGRESQL_*` (el constructor de `PostgresqlClient` ya lo hace).
2. Nunca imprimas `RUVIC_POSTGRESQL_PASSWORD` en logs ni en la salida.
3. La librería es de SOLO LECTURA: no intentes INSERT/UPDATE/DELETE con ella.
4. Usa `limit` razonable en `read_table` (default 100) para no traer tablas enteras.
5. Para analizar rendimiento de un query usa `explain_query`, nunca lo ejecutes directamente.
6. Los nombres de tabla/esquema se validan como identificadores simples (letras, números, guion bajo); no aceptan `schema.table` combinado en un solo parámetro.

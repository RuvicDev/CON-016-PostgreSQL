# Conector PostgreSQL (CON-016)

Conector Ruvic de solo lectura para PostgreSQL. Permite listar tablas,
leer datos con límite, obtener estadísticas de tablas y analizar el plan
de ejecución de un query sin ejecutarlo.

## Instalación

```bash
pip install git+https://github.com/Dgirto/PostgreSQL.git#subdirectory=lib
```

Python 3.10+. Dependencia única: `psycopg[binary]>=3.1,<4.0`.

## Permisos requeridos en el servidor

Crea un usuario dedicado de solo lectura (no reutilizar un usuario admin o
de aplicación):

```sql
CREATE USER ruvic_reader WITH PASSWORD 'CAMBIA_ESTA_CONTRASEÑA';
GRANT CONNECT ON DATABASE tu_base_de_datos TO ruvic_reader;
GRANT USAGE ON SCHEMA public TO ruvic_reader;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO ruvic_reader;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT SELECT ON TABLES TO ruvic_reader;
```

- `CONNECT` sobre la base de datos: abrir la conexión.
- `USAGE` sobre el esquema: acceder a sus objetos.
- `SELECT` sobre las tablas a exponer: necesario para `db.read`, `db.stats`
  y `db.explain`. El `ALTER DEFAULT PRIVILEGES` hace que las tablas creadas
  después también sean legibles sin repetir el GRANT.
- Las vistas de catálogo que usa el conector (`pg_stat_user_tables`,
  `information_schema.columns`, `pg_total_relation_size`) están
  disponibles para cualquier usuario autenticado sobre sus objetos
  visibles; no requieren permisos adicionales.
- No se otorgan permisos de escritura ni administración.

## Variables de entorno (`RUVIC_POSTGRESQL_*`)

| Variable | Obligatoria | Descripción |
|----------|-------------|-------------|
| `RUVIC_POSTGRESQL_HOST` | Sí | Host del servidor |
| `RUVIC_POSTGRESQL_PORT` | No (default `5432`) | Puerto |
| `RUVIC_POSTGRESQL_DATABASE` | Sí | Base de datos a consultar |
| `RUVIC_POSTGRESQL_USERNAME` | Sí | Usuario |
| `RUVIC_POSTGRESQL_PASSWORD` | Sí | Contraseña |
| `RUVIC_POSTGRESQL_CONNECT_TIMEOUT` | No (default `10`) | Timeout de conexión en segundos |

## Pruebas locales

Con Docker:

```bash
docker run -d --name postgres-test \
  -e POSTGRES_PASSWORD=root123 \
  -e POSTGRES_DB=demo \
  -p 5432:5432 \
  postgres:16

docker exec -i postgres-test psql -U postgres -d demo <<'SQL'
CREATE TABLE clientes (id SERIAL PRIMARY KEY, nombre VARCHAR(100), ciudad VARCHAR(100));
INSERT INTO clientes (nombre, ciudad) VALUES ('ACME', 'Bogota'), ('Globex', 'Medellin');
SQL
```

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ./lib

export RUVIC_POSTGRESQL_HOST=localhost
export RUVIC_POSTGRESQL_PORT=5432
export RUVIC_POSTGRESQL_DATABASE=demo
export RUVIC_POSTGRESQL_USERNAME=postgres
export RUVIC_POSTGRESQL_PASSWORD=root123

python test_connection.py
python validate_local.py
```

Prueba también los casos de error (contraseña incorrecta, host inalcanzable,
tabla inexistente) y verifica que los mensajes sean claros.

## Notas de integración

- La sesión se abre con `options="-c default_transaction_read_only=on"`
  como segunda barrera de seguridad (la primera es que el usuario de BD
  solo tiene `SELECT`).
- `explain_query` valida que el statement sea un único `SELECT` (rechaza
  `;` múltiples) y usa `EXPLAIN (FORMAT JSON)` sin `ANALYZE` — nunca
  ejecuta el query.
- Los nombres de tabla/esquema se validan con una expresión regular
  estricta antes de interpolarlos en el SQL (identificadores entre
  comillas dobles), para evitar inyección SQL.
- Sin límites de tasa conocidos del lado del conector; los límites de
  conexiones concurrentes dependen de `max_connections` del servidor.

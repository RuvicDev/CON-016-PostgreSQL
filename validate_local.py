"""Validación local del conector postgresql: ejercita las 4 capacidades.

Uso:
    python validate_local.py

Requiere las variables RUVIC_POSTGRESQL_* exportadas en el entorno, y una
tabla "clientes" accesible en el esquema "public".
"""

from ruvic_postgresql_connector import PostgresqlClient, setup_logging

setup_logging("INFO")
client = PostgresqlClient()

print("== 1. Tablas ==")
for t in client.list_tables():
    print(f"  {t['schema']}.{t['table']} (~{t['rows_estimate']} filas)")

print("== 2. Datos de clientes ==")
for row in client.read_table("clientes", limit=10):
    print(f"  {row}")

print("== 3. Estadisticas ==")
stats = client.table_stats("clientes")
print(f"  filas={stats['row_count']} tamano={stats['total_size']}")
print(f"  columnas={[c['name'] for c in stats['columns']]}")

print("== 4. EXPLAIN ==")
plan = client.explain_query("SELECT * FROM clientes WHERE ciudad = 'Bogota'")
print(f"  costo={plan['total_cost']}")

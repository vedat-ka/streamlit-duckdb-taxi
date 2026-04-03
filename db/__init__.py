"""
db/__init__.py
──────────────
Macht das 'db'-Verzeichnis zu einem Python-Paket und
exportiert die wichtigsten Symbole direkt auf Paket-Ebene.

Damit kann in app.py kürzer importiert werden:

  # Ohne __init__.py wäre nötig:
  from db.connection import open_connection
  from db.sources    import build_source, build_where
  from db.queries    import sql_kpis, sql_daily_trips, ...

  # Mit __init__.py genügt:
  from db import open_connection, build_source, build_where
  from db import queries   # und dann queries.sql_kpis(...)

Modulübersicht:
  db/connection.py  – DuckDB-Verbindung öffnen, Views anlegen
  db/sources.py     – FROM-Klausel und WHERE-Filter bauen
  db/queries.py     – alle SQL-Abfragen als Funktionen
"""

from db.connection import open_connection          # noqa: F401
from db.sources    import (                        # noqa: F401
    build_source,
    build_where,
    where_for_pickup,
    where_for_dropoff,
)
from db             import queries                 # noqa: F401

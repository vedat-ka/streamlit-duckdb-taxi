"""
db/connection.py
────────────────
Verantwortlich für ALLES rund um die DuckDB-Datenbankverbindung:

  1. Eine In-Memory-Verbindung öffnen  (open_connection)
  2. Die drei DuckDB-Views anlegen      (create_views)
     • yellow  → Yellow-Taxi Parquet-Datei
     • green   → Green-Taxi  Parquet-Datei
     • zones   → Zonen-Lookup CSV-Datei

Warum In-Memory und keine Datei?
  Die Parquet-Dateien liegen direkt auf dem Dateisystem.
  DuckDB kann diese ohne Konvertierung direkt per VIEW abfragen.
  Eine persistente .duckdb-Datei wäre hier unnötig.

Verwendung:
  from db.connection import open_connection
  con = open_connection(file_yellow, file_green, file_zones)
  df  = con.execute("SELECT COUNT(*) FROM yellow").df()
"""

import duckdb


def create_views(
    con: duckdb.DuckDBPyConnection,
    file_yellow: str,
    file_green: str,
    file_zones: str,
) -> None:
    """
    Legt drei DuckDB-Views auf die Rohdateien an.

    Views verhalten sich wie Tabellen – jede SQL-Abfrage
    dahinter liest direkt aus den Parquet-/CSV-Dateien,
    ohne die Daten in den Speicher zu kopieren.

    Parameter:
        con         – offene DuckDB-Verbindung
        file_yellow – absoluter Pfad zur Yellow-Taxi Parquet-Datei
        file_green  – absoluter Pfad zur Green-Taxi  Parquet-Datei
        file_zones  – absoluter Pfad zur Zonen-Lookup CSV-Datei
    """
    if file_yellow:
        con.execute(
            f"CREATE OR REPLACE VIEW yellow AS "
            f"SELECT * FROM read_parquet('{file_yellow}')"
        )
    if file_green:
        con.execute(
            f"CREATE OR REPLACE VIEW green AS "
            f"SELECT * FROM read_parquet('{file_green}')"
        )
    con.execute(
        f"CREATE OR REPLACE VIEW zones AS "
        f"SELECT * FROM read_csv_auto('{file_zones}')"
    )


def open_connection(
    file_yellow: str,
    file_green: str,
    file_zones: str,
) -> duckdb.DuckDBPyConnection:
    """
    Öffnet eine neue In-Memory-DuckDB-Verbindung und
    initialisiert sofort alle drei Views (yellow, green, zones).

    Gibt die fertig eingerichtete Verbindung zurück.
    Der Aufrufer (TaxiDataRepository) ist für das Caching zuständig.

    Parameter:
        file_yellow – absoluter Pfad zur Yellow-Taxi Parquet-Datei
        file_green  – absoluter Pfad zur Green-Taxi  Parquet-Datei
        file_zones  – absoluter Pfad zur Zonen-Lookup CSV-Datei

    Rückgabe:
        duckdb.DuckDBPyConnection – einsatzbereite Verbindung
    """
    con = duckdb.connect()          # In-Memory, keine Datei auf Disk
    create_views(con, file_yellow, file_green, file_zones)
    return con

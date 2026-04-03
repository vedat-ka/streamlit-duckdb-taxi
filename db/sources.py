"""
db/sources.py
─────────────
Baut die FROM-Klausel und den WHERE-Filter für eine SQL-Abfrage,
abhängig davon welchen Datensatz der Nutzer in der Sidebar gewählt hat.

Hintergrund:
  Yellow und Green Taxi speichern den Abholzeitpunkt unter
  verschiedenen Spaltennamen:
    • Yellow → tpep_pickup_datetime
    • Green  → lpep_pickup_datetime
  Bei "Beide" werden beide Tabellen per UNION ALL zusammengeführt
  und der Zeitstempel auf einen gemeinsamen Alias normiert.

Öffentliche Funktionen:
  build_source(dataset)              → (from_clause, ts_col)
  build_where(ts_col, max_dist, min_fare) → WHERE-String
  where_for_pickup(where)            → WHERE mit PULocationID-Guard
  where_for_dropoff(where)           → WHERE mit DOLocationID-Guard

Verwendung:
  from db.sources import build_source, build_where
  from_clause, ts_col = build_source("Yellow Taxi")
  where = build_where(ts_col, max_dist=50, min_fare=0.0)
"""

# ── UNION ALL – wird bei Datensatz "Beide" als FROM-Klausel verwendet ─────────
#
# Beide Tabellen haben leicht unterschiedliche Spalten.
# Wir wählen nur die gemeinsamen Felder aus und vereinheitlichen
# den Zeitstempel-Spaltennamen auf "pickup_datetime".
#
_COMBINED_SOURCE = (
    "("
    # ── Yellow Taxi ────────────────────────────────────────────────────────────
    "SELECT "
    "  VendorID, "
    "  tpep_pickup_datetime  AS pickup_datetime, "
    "  tpep_dropoff_datetime AS dropoff_datetime, "
    "  passenger_count, "
    "  trip_distance, "
    "  payment_type, "
    "  fare_amount, "
    "  tip_amount, "
    "  total_amount, "
    "  PULocationID, "
    "  DOLocationID, "
    "  'yellow' AS taxi_type "
    "FROM yellow "
    # ── Green Taxi ─────────────────────────────────────────────────────────────
    "UNION ALL "
    "SELECT "
    "  VendorID, "
    "  lpep_pickup_datetime  AS pickup_datetime, "
    "  lpep_dropoff_datetime AS dropoff_datetime, "
    "  passenger_count, "
    "  trip_distance, "
    "  payment_type, "
    "  fare_amount, "
    "  tip_amount, "
    "  total_amount, "
    "  PULocationID, "
    "  DOLocationID, "
    "  'green' AS taxi_type "
    "FROM green"
    ")"
)


def build_source(dataset: str) -> tuple[str, str]:
    """
    Liefert die SQL-FROM-Klausel und den Zeitstempel-Spaltennamen
    passend zum gewählten Datensatz.

    Parameter:
        dataset – Auswahl aus der Sidebar:
                  "Yellow Taxi" | "Green Taxi" | "Beide"

    Rückgabe:
        (from_clause, ts_col)
        from_clause – Tabellenname oder UNION-ALL-Unterabfrage
        ts_col      – Name der Zeitstempel-Spalte in dieser Quelle
    """
    if dataset == "Yellow Taxi":
        return "yellow", "tpep_pickup_datetime"

    if dataset == "Green Taxi":
        return "green", "lpep_pickup_datetime"

    # "Beide" → UNION ALL mit vereinheitlichtem Spaltennamen
    return _COMBINED_SOURCE, "pickup_datetime"


def build_where(ts_col: str, max_dist: int, min_fare: float, month: str = "") -> str:
    """
    Erstellt den WHERE-String mit den Basis-Filtern.

    Filter:
      • Zeitstempel darf nicht NULL sein
      • Wenn month angegeben (Format 'YYYY-MM'), wird auf diesen Kalendermonat eingeschränkt
      • Fahrstrecke muss > 0 und ≤ max_dist sein
      • Fahrpreis muss ≥ min_fare sein

    Parameter:
        ts_col   – Name der Zeitstempel-Spalte (unterscheidet sich je Quelle)
        max_dist – maximale Fahrstrecke in Meilen (aus dem Sidebar-Slider)
        min_fare – Mindestfahrpreis in USD (aus dem Sidebar-Eingabefeld)
        month    – gewählter Monat im Format 'YYYY-MM', z. B. '2025-11'

    Rückgabe:
        str – vollständiger WHERE-Ausdruck, bereit für f-String-Einbettung
    """
    month_filter = ""
    if month:
        year, mon = month.split("-")
        month_filter = (
            f"AND YEAR({ts_col}) = {year} AND MONTH({ts_col}) = {int(mon)} "
        )
    return (
        f"WHERE {ts_col} IS NOT NULL "
        f"{month_filter}"
        f"AND trip_distance > 0 AND trip_distance <= {max_dist} "
        f"AND fare_amount >= {min_fare}"
    )


def where_for_pickup(where: str) -> str:
    """
    Erweitert den WHERE-Filter um eine PULocationID-Prüfung.
    Nötig, weil beim JOIN mit der Zonen-Tabelle NULL-Werte
    zu ungematchten Zeilen führen würden.

    Parameter:
        where – bereits gebauter WHERE-String von build_where()

    Rückgabe:
        WHERE-String mit zusätzlichem "t.PULocationID IS NOT NULL"
    """
    return where.replace("WHERE", "WHERE t.PULocationID IS NOT NULL AND", 1)


def where_for_dropoff(where: str) -> str:
    """
    Wie where_for_pickup, aber für die Ziel-Zone (DOLocationID).

    Parameter:
        where – bereits gebauter WHERE-String von build_where()

    Rückgabe:
        WHERE-String mit zusätzlichem "t.DOLocationID IS NOT NULL"
    """
    return where.replace("WHERE", "WHERE t.DOLocationID IS NOT NULL AND", 1)

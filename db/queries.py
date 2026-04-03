"""
db/queries.py
─────────────
Enthält alle SQL-Abfragen des Dashboards als eigenständige Funktionen.

Design-Entscheidung:
  Jede Funktion nimmt die drei Basis-Parameter entgegen, die
  TaxiDataRepository für jede Abfrage kennt:
    • from_clause  – Tabellenname oder UNION-ALL-Unterabfrage
    • ts_col       – Name der Zeitstempel-Spalte
    • where        – vollständiger WHERE-String

  Die Funktionen geben einen fertigen SQL-String zurück,
  den TaxiDataRepository an DuckDB übergibt.

  So lassen sich SQL-Abfragen unabhängig vom Rest testen und
  lesen, ohne durch Repository-Logik navigieren zu müssen.

Verfügbare Abfragen:
  sql_kpis                – KPI-Kennzahlen (Fahrten, Umsatz, Ø-Werte)
  sql_daily_trips         – Fahrtenanzahl pro Tag
  sql_hourly_trips        – Fahrtenanzahl pro Stunde
  sql_payment_dist        – Zahlungsarten mit Häufigkeit
  sql_distance_dist       – Fahrstrecken-Verteilung (Histogramm)
  sql_top_pickup_zones    – Top-N Abholzonen mit Borough-Join
  sql_top_dropoff_zones   – Top-N Zielzonen  mit Borough-Join
  sql_hourly_fare_tip     – Ø Fahrpreis und Ø Trinkgeld pro Stunde
  sql_passenger_dist      – Verteilung der Passagieranzahl
  sql_weekday_stats       – Fahrten und Ø Fahrpreis pro Wochentag
"""


def sql_kpis(from_clause: str, where: str) -> str:
    """
    Liefert die fünf KPI-Kennzahlen für die Metriken-Zeile:
      total_trips   – Gesamtanzahl der Fahrten
      total_revenue – Gesamtumsatz (total_amount)
      avg_fare      – Durchschnittlicher Fahrpreis
      avg_distance  – Durchschnittliche Fahrstrecke in Meilen
      avg_tip       – Durchschnittliches Trinkgeld
    """
    return f"""
        SELECT
            COUNT(*)            AS total_trips,
            SUM(total_amount)   AS total_revenue,
            AVG(fare_amount)    AS avg_fare,
            AVG(trip_distance)  AS avg_distance,
            AVG(tip_amount)     AS avg_tip
        FROM {from_clause}
        {where}
    """


def sql_daily_trips(from_clause: str, ts_col: str, where: str) -> str:
    """
    Fahrtenanzahl je Kalendertag.
    Ergebnis: Spalten 'tag' (DATE) und 'fahrten' (INTEGER).
    """
    return f"""
        SELECT
            CAST({ts_col} AS DATE) AS tag,
            COUNT(*)               AS fahrten
        FROM {from_clause}
        {where}
        GROUP BY tag
        ORDER BY tag
    """


def sql_hourly_trips(from_clause: str, ts_col: str, where: str) -> str:
    """
    Fahrtenanzahl je Stunde des Tages (0–23).
    Ergebnis: Spalten 'stunde' (0–23) und 'fahrten' (INTEGER).
    """
    return f"""
        SELECT
            EXTRACT(hour FROM {ts_col}) AS stunde,
            COUNT(*)                    AS fahrten
        FROM {from_clause}
        {where}
        GROUP BY stunde
        ORDER BY stunde
    """


def sql_payment_dist(from_clause: str, where: str) -> str:
    """
    Häufigkeit jeder Zahlungsart (Codes 1–6).
    Ergebnis: Spalten 'payment_type' (INTEGER) und 'anzahl' (INTEGER).

    Hinweis: Die lesbaren Namen (z. B. "Kreditkarte") werden
    im Repository per PAYMENT_MAP ergänzt.
    """
    return f"""
        SELECT
            payment_type,
            COUNT(*) AS anzahl
        FROM {from_clause}
        {where}
            AND payment_type IS NOT NULL
            AND payment_type BETWEEN 1 AND 6
        GROUP BY payment_type
        ORDER BY anzahl DESC
    """


def sql_distance_dist(from_clause: str, where: str) -> str:
    """
    Häufigkeitsverteilung der Fahrstrecken (gerundet auf ganze Meilen).
    Begrenzt auf < 30 Meilen, um Ausreißer auszublenden.
    Ergebnis: Spalten 'km_bin' (0, 1, 2, …) und 'anzahl' (INTEGER).
    """
    return f"""
        SELECT
            FLOOR(trip_distance)::INTEGER AS km_bin,
            COUNT(*)                      AS anzahl
        FROM {from_clause}
        {where}
            AND trip_distance < 30
        GROUP BY km_bin
        ORDER BY km_bin
    """


def sql_top_pickup_zones(
    from_clause: str,
    where_with_pu_guard: str,
    limit: int,
) -> str:
    """
    Top-N häufigste Abholzonen.
    Joined die Fahrten-Tabelle (Alias 't') mit der Zonen-View
    über PULocationID → LocationID.
    Ergebnis: Spalten 'Zone', 'Borough', 'fahrten'.

    Parameter:
        where_with_pu_guard – WHERE-String inkl. "t.PULocationID IS NOT NULL"
                              (von sources.where_for_pickup())
        limit               – Anzahl der Top-Zonen
    """
    return f"""
        SELECT
            z.Zone,
            z.Borough,
            COUNT(*) AS fahrten
        FROM {from_clause} t
        JOIN zones z ON t.PULocationID = z.LocationID
        {where_with_pu_guard}
        GROUP BY z.Zone, z.Borough
        ORDER BY fahrten DESC
        LIMIT {limit}
    """


def sql_top_dropoff_zones(
    from_clause: str,
    where_with_do_guard: str,
    limit: int,
) -> str:
    """
    Top-N häufigste Zielzonen.
    Wie sql_top_pickup_zones, aber über DOLocationID.
    Ergebnis: Spalten 'Zone', 'Borough', 'fahrten'.

    Parameter:
        where_with_do_guard – WHERE-String inkl. "t.DOLocationID IS NOT NULL"
                              (von sources.where_for_dropoff())
    """
    return f"""
        SELECT
            z.Zone,
            z.Borough,
            COUNT(*) AS fahrten
        FROM {from_clause} t
        JOIN zones z ON t.DOLocationID = z.LocationID
        {where_with_do_guard}
        GROUP BY z.Zone, z.Borough
        ORDER BY fahrten DESC
        LIMIT {limit}
    """


def sql_hourly_fare_tip(from_clause: str, ts_col: str, where: str) -> str:
    """
    Durchschnittlicher Fahrpreis und Trinkgeld je Tagesstunde.
    Nur Fahrten mit fare_amount > 0 werden berücksichtigt.
    Ergebnis: Spalten 'stunde', 'avg_fare', 'avg_tip'.
    """
    return f"""
        SELECT
            EXTRACT(hour FROM {ts_col}) AS stunde,
            AVG(fare_amount)            AS avg_fare,
            AVG(tip_amount)             AS avg_tip
        FROM {from_clause}
        {where}
            AND fare_amount > 0
        GROUP BY stunde
        ORDER BY stunde
    """


def sql_passenger_dist(from_clause: str, where: str) -> str:
    """
    Verteilung der Passagieranzahl pro Fahrt (1–8 Personen).
    Ergebnis: Spalten 'passagiere' (1–8) und 'fahrten' (INTEGER).
    """
    return f"""
        SELECT
            passenger_count::INTEGER AS passagiere,
            COUNT(*)                 AS fahrten
        FROM {from_clause}
        {where}
            AND passenger_count BETWEEN 1 AND 8
        GROUP BY passagiere
        ORDER BY passagiere
    """


def sql_weekday_stats(from_clause: str, ts_col: str, where: str) -> str:
    """
    Fahrtenanzahl und Durchschnittspreis je Wochentag.
    DOW-Kodierung: 0 = Sonntag, 1 = Mo, …, 6 = Sa (DuckDB-Standard).
    Ergebnis: Spalten 'dow_num' (0–6), 'fahrten', 'avg_fare'.

    Hinweis: Die lesbaren Tagnamen (Mo, Di, …) werden im
    Repository per DAY_MAP ergänzt.
    """
    return f"""
        SELECT
            EXTRACT(dow FROM {ts_col}) AS dow_num,
            COUNT(*)                   AS fahrten,
            AVG(fare_amount)           AS avg_fare
        FROM {from_clause}
        {where}
        GROUP BY dow_num
        ORDER BY dow_num
    """

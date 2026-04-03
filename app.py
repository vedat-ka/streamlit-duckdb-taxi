import os
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
import duckdb

# ── Datenbankmodule (eigenes Paket) ───────────────────────────────────────────
#   db/connection.py  – Verbindung öffnen, Views anlegen
#   db/sources.py     – FROM-Klausel und WHERE-Filter bauen
#   db/queries.py     – alle SQL-Abfragen als Funktionen
from db import open_connection, build_source, build_where, where_for_pickup, where_for_dropoff
from db import queries


# ══════════════════════════════════════════════════════════════════════════════
# Konfiguration
# ══════════════════════════════════════════════════════════════════════════════

BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
DATA_DIR   = os.path.join(BASE_DIR, "data")
FILE_ZONES = os.path.join(BASE_DIR, "taxi_zone_lookup.csv")


@st.cache_data(ttl=600)
def _count_trips(parquet_file: str) -> int:
    """Zählt die Zeilen in einer Parquet-Datei (gecacht pro Datei)."""
    try:
        import duckdb
        return duckdb.execute(
            f"SELECT COUNT(*) FROM read_parquet('{parquet_file}')"
        ).fetchone()[0]
    except Exception:
        return 0


def _fmt_count(n: int) -> str:
    """Formatiert eine Fahrtanzahl lesbar: 1.234.567 → '1,2 Mio', 40000 → '40 Tsd'."""
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f} Mio"
    if n >= 1_000:
        return f"{n // 1_000} Tsd"
    return str(n)


def _get_available_months() -> list:
    """Liefert alle Monate zurück, für die yellow- UND green-Taxi-Daten vorhanden sind."""
    import re
    if not os.path.isdir(DATA_DIR):
        return []
    months: set = set()
    for fname in os.listdir(DATA_DIR):
        m = re.match(r'(?:yellow|green)_tripdata_(\d{4}-\d{2})\.parquet$', fname)
        if m:
            months.add(m.group(1))
    return sorted(
        month for month in months
        if os.path.exists(os.path.join(DATA_DIR, f"yellow_tripdata_{month}.parquet"))
        and os.path.exists(os.path.join(DATA_DIR, f"green_tripdata_{month}.parquet"))
    )

@st.cache_data(ttl=600)
def _get_monthly_kpis(dataset: str, months: tuple) -> pd.DataFrame:
    """KPI-Kennzahlen je verfügbarem Monat (für Monatsvergleich-Diagramme)."""
    rows = []
    for month in months:
        fy = os.path.join(DATA_DIR, f"yellow_tripdata_{month}.parquet")
        fg = os.path.join(DATA_DIR, f"green_tripdata_{month}.parquet")
        year, mon = month.split("-")
        if dataset == "Yellow Taxi":
            source = f"read_parquet('{fy}')"
            ts_col = "tpep_pickup_datetime"
        elif dataset == "Green Taxi":
            source = f"read_parquet('{fg}')"
            ts_col = "lpep_pickup_datetime"
        else:
            source = (
                f"(SELECT tpep_pickup_datetime AS pickup_datetime, "
                f"fare_amount, tip_amount, total_amount, trip_distance "
                f"FROM read_parquet('{fy}') UNION ALL "
                f"SELECT lpep_pickup_datetime AS pickup_datetime, "
                f"fare_amount, tip_amount, total_amount, trip_distance "
                f"FROM read_parquet('{fg}'))"
            )
            ts_col = "pickup_datetime"
        try:
            row = duckdb.execute(f"""
                SELECT
                    '{month}' AS monat,
                    COUNT(*) AS total_trips,
                    SUM(total_amount) AS total_revenue,
                    AVG(fare_amount) AS avg_fare,
                    AVG(trip_distance) AS avg_distance,
                    AVG(tip_amount) AS avg_tip
                FROM {source}
                WHERE {ts_col} IS NOT NULL
                AND YEAR({ts_col}) = {year} AND MONTH({ts_col}) = {int(mon)}
                AND trip_distance > 0
                AND fare_amount >= 0
            """).df().iloc[0].to_dict()
            rows.append(row)
        except Exception:
            pass
    return pd.DataFrame(rows) if rows else pd.DataFrame()


PAYMENT_MAP = {
    1: "Kreditkarte", 2: "Bar", 3: "Keine Gebühr",
    4: "Streit",       5: "Unbekannt", 6: "Storniert",
}
DAY_MAP = {0: "So", 1: "Mo", 2: "Di", 3: "Mi", 4: "Do", 5: "Fr", 6: "Sa"}
DAY_ORDER = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]

COLORS = {
    "primary":   "#2563EB",
    "secondary": "#0EA5E9",
    "accent":    "#0284C7",
    "dark":      "#1D4ED8",
    "border":    "#1E3A8A",
    "pie": ["#2563EB", "#0EA5E9", "#38BDF8", "#7DD3FC", "#BAE6FD", "#93C5FD"],
    "zone": ["#2563EB", "#0EA5E9", "#38BDF8", "#7DD3FC", "#1D4ED8"],
}

LIGHT_LAYOUT = dict(
    paper_bgcolor="#FFFFFF",
    plot_bgcolor="#F8FAFC",
    font=dict(color="#1E293B", family="sans-serif"),
    xaxis=dict(gridcolor="#E2E8F0", linecolor="#CBD5E1", zerolinecolor="#E2E8F0"),
    yaxis=dict(gridcolor="#E2E8F0", linecolor="#CBD5E1", zerolinecolor="#E2E8F0"),
    margin=dict(t=10, b=10, l=10, r=10),
)


# ══════════════════════════════════════════════════════════════════════════════
# 1. Datenzugriff – TaxiDataRepository
# ══════════════════════════════════════════════════════════════════════════════

class TaxiDataRepository:
    """
    Verwaltet die DuckDB-Verbindung und führt alle Abfragen aus.

    Die eigentliche SQL-Logik ist ausgelagert:
      • db/connection.py  → Verbindung + Views
      • db/sources.py     → FROM-Klausel und WHERE-Filter
      • db/queries.py     → SQL-Strings je Auswertung

    Diese Klasse ist nur noch für:
      1. Caching der Verbindung (einmalig pro Session)
      2. Caching der Abfrageergebnisse (TTL 10 min)
      3. Weitergabe der Parameter an die Query-Funktionen
    """

    # ── Verbindung einmalig pro Streamlit-Session öffnen ──────────────────────
    # open_connection() kommt aus db/connection.py und legt
    # die Views yellow, green und zones an.
    @staticmethod
    @st.cache_resource
    def _get_connection(file_yellow: str, file_green: str, file_zones: str) -> duckdb.DuckDBPyConnection:
        return open_connection(file_yellow, file_green, file_zones)

    # ── Abfrageergebnis 10 Minuten cachen ─────────────────────────────────────
    @staticmethod
    @st.cache_data(ttl=600)
    def _query(sql: str, file_yellow: str, file_green: str, file_zones: str) -> pd.DataFrame:
        return TaxiDataRepository._get_connection(file_yellow, file_green, file_zones).execute(sql).df()

    def __init__(self, dataset: str, max_dist: int, min_fare: float,
                 file_yellow: str, file_green: str, month: str = "") -> None:
        self._file_yellow = file_yellow
        self._file_green  = file_green
        # build_source()  → db/sources.py: FROM-Klausel + Zeitstempel-Spaltenname
        # build_where()   → db/sources.py: WHERE-Filter mit den drei Basis-Bedingungen
        self._from_clause, self._ts_col = build_source(dataset)
        self._where = build_where(self._ts_col, max_dist, min_fare, month)

    def _q(self, sql: str) -> pd.DataFrame:
        """Kurzform: SQL ausführen und DataFrame zurückgeben."""
        return self._query(sql, self._file_yellow, self._file_green, FILE_ZONES)

    # ── öffentliche Abfragemethoden ────────────────────────────────────────────
    # Jede Methode delegiert den SQL-Aufbau an db/queries.py.

    def get_kpis(self) -> pd.Series:
        """KPI-Kennzahlen: Fahrten, Umsatz, Ø Preis, Ø Distanz, Ø Trinkgeld."""
        return self._q(
            queries.sql_kpis(self._from_clause, self._where)
        ).iloc[0]

    def get_daily_trips(self) -> pd.DataFrame:
        """Fahrtenanzahl je Kalendertag."""
        return self._q(
            queries.sql_daily_trips(self._from_clause, self._ts_col, self._where)
        )

    def get_hourly_trips(self) -> pd.DataFrame:
        """Fahrtenanzahl je Tagesstunde (0–23)."""
        return self._q(
            queries.sql_hourly_trips(self._from_clause, self._ts_col, self._where)
        )

    def get_payment_distribution(self) -> pd.DataFrame:
        """Zahlungsarten mit lesbaren Bezeichnungen (via PAYMENT_MAP)."""
        df = self._q(
            queries.sql_payment_dist(self._from_clause, self._where)
        )
        df["Zahlungsart"] = df["payment_type"].map(PAYMENT_MAP).fillna("Sonstige")
        return df

    def get_distance_distribution(self) -> pd.DataFrame:
        """Histogramm der Fahrstrecken (0–30 Meilen)."""
        return self._q(
            queries.sql_distance_dist(self._from_clause, self._where)
        )

    def get_top_pickup_zones(self, limit: int = 15) -> pd.DataFrame:
        """Top-N Abholzonen. where_for_pickup() ergänzt NULL-Guard für den JOIN."""
        return self._q(
            queries.sql_top_pickup_zones(
                self._from_clause,
                where_for_pickup(self._where),   # db/sources.py
                limit,
            )
        )

    def get_top_dropoff_zones(self, limit: int = 15) -> pd.DataFrame:
        """Top-N Zielzonen. where_for_dropoff() ergänzt NULL-Guard für den JOIN."""
        return self._q(
            queries.sql_top_dropoff_zones(
                self._from_clause,
                where_for_dropoff(self._where),  # db/sources.py
                limit,
            )
        )

    def get_hourly_fare_tip(self) -> pd.DataFrame:
        """Ø Fahrpreis und Ø Trinkgeld je Tagesstunde."""
        return self._q(
            queries.sql_hourly_fare_tip(self._from_clause, self._ts_col, self._where)
        )

    def get_passenger_distribution(self) -> pd.DataFrame:
        """Verteilung der Passagieranzahl (1–8 Personen)."""
        return self._q(
            queries.sql_passenger_dist(self._from_clause, self._where)
        )

    def get_weekday_stats(self) -> pd.DataFrame:
        """Fahrten und Ø Fahrpreis je Wochentag (inkl. lesbarer Tagnamen)."""
        df = self._q(
            queries.sql_weekday_stats(self._from_clause, self._ts_col, self._where)
        )
        df["Wochentag"] = df["dow_num"].map(DAY_MAP)
        return df

    def get_raw_data(self, limit: int = 30) -> pd.DataFrame:
        """Erste N Rohdaten-Zeilen direkt aus der gewählten Quelle."""
        return self._q(f"SELECT * FROM {self._from_clause} LIMIT {limit}")


# ══════════════════════════════════════════════════════════════════════════════
# 2. Diagramme – ChartBuilder
# ══════════════════════════════════════════════════════════════════════════════

class ChartBuilder:
    """Erstellt alle Plotly-Figures für das Dashboard."""

    @staticmethod
    def _layout(**overrides) -> dict:
        """Gibt LIGHT_LAYOUT mit optionalen Overrides zurück."""
        layout = {**LIGHT_LAYOUT}
        for key, value in overrides.items():
            if key in ("xaxis", "yaxis") and key in layout:
                layout[key] = {**layout[key], **value}
            else:
                layout[key] = value
        return layout

    def daily_trips(self, df: pd.DataFrame) -> go.Figure:
        fig = px.bar(df, x="tag", y="fahrten",
                     labels={"tag": "Datum", "fahrten": "Anzahl Fahrten"},
                     color_discrete_sequence=[COLORS["primary"]])
        fig.update_layout(**self._layout())
        return fig

    def hourly_trips(self, df: pd.DataFrame) -> go.Figure:
        fig = px.bar(df, x="stunde", y="fahrten",
                     labels={"stunde": "Uhrzeit (h)", "fahrten": "Anzahl Fahrten"},
                     color_discrete_sequence=[COLORS["secondary"]])
        fig.update_layout(**self._layout(xaxis={"tickmode": "linear", "dtick": 1}))
        return fig

    def payment_pie(self, df: pd.DataFrame) -> go.Figure:
        fig = px.pie(df, values="anzahl", names="Zahlungsart",
                     color_discrete_sequence=COLORS["pie"], hole=0.45)
        fig.update_layout(**self._layout(
            paper_bgcolor="#FFFFFF",
            legend=dict(orientation="v", x=1.02, y=0.5)
        ))
        fig.update_traces(textposition="inside", textinfo="percent+label")
        return fig

    def distance_histogram(self, df: pd.DataFrame) -> go.Figure:
        fig = px.bar(df, x="km_bin", y="anzahl",
                     labels={"km_bin": "Fahrstrecke (Meilen)", "anzahl": "Anzahl Fahrten"},
                     color_discrete_sequence=[COLORS["accent"]])
        fig.update_layout(**self._layout())
        return fig

    def zone_bar(self, df: pd.DataFrame, title_col: str = "Zone") -> go.Figure:
        fig = px.bar(df, x="fahrten", y=title_col, orientation="h",
                     color="Borough",
                     labels={"fahrten": "Anzahl Fahrten", title_col: ""},
                     color_discrete_sequence=COLORS["zone"])
        fig.update_layout(**self._layout(
            yaxis={"autorange": "reversed"},
            legend=dict(orientation="h", yanchor="bottom", y=1.02)
        ))
        return fig

    def hourly_fare_line(self, df: pd.DataFrame) -> go.Figure:
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=df["stunde"], y=df["avg_fare"],
            mode="lines+markers", name="Ø Fahrpreis",
            line=dict(color=COLORS["primary"], width=2.5),
            marker=dict(size=6, color=COLORS["primary"]),
        ))
        fig.add_trace(go.Scatter(
            x=df["stunde"], y=df["avg_tip"],
            mode="lines+markers", name="Ø Trinkgeld",
            line=dict(color=COLORS["secondary"], width=2.5, dash="dot"),
            marker=dict(size=6, color=COLORS["secondary"]),
        ))
        fig.update_layout(**self._layout(
            xaxis={"title": "Uhrzeit (h)", "tickmode": "linear", "dtick": 1},
            yaxis={"title": "Betrag ($)"},
            legend=dict(orientation="h", yanchor="bottom", y=1.02),
        ))
        return fig

    def passenger_bar(self, df: pd.DataFrame) -> go.Figure:
        fig = px.bar(df, x="passagiere", y="fahrten",
                     labels={"passagiere": "Passagiere", "fahrten": "Anzahl Fahrten"},
                     text="fahrten",
                     color_discrete_sequence=[COLORS["dark"]])
        fig.update_traces(
            texttemplate="%{text:,.0f}", textposition="outside",
            marker_line_color=COLORS["border"], marker_line_width=1.2,
        )
        fig.update_layout(**self._layout(
            xaxis={"tickmode": "linear", "dtick": 1, "title": "Passagiere"},
            yaxis={"title": "Anzahl Fahrten"},
        ))
        return fig

    def weekday_trips(self, df: pd.DataFrame) -> go.Figure:
        fig = px.bar(df, x="Wochentag", y="fahrten",
                     labels={"fahrten": "Anzahl Fahrten"},
                     color_discrete_sequence=[COLORS["primary"]],
                     category_orders={"Wochentag": DAY_ORDER})
        fig.update_layout(**self._layout())
        return fig

    def weekday_fare(self, df: pd.DataFrame) -> go.Figure:
        fig = px.bar(df, x="Wochentag", y="avg_fare",
                     labels={"avg_fare": "Ø Fahrpreis ($)"},
                     color_discrete_sequence=[COLORS["secondary"]],
                     category_orders={"Wochentag": DAY_ORDER})
        fig.update_layout(**self._layout())
        return fig

    def monthly_kpi_bar(self, df: pd.DataFrame, col: str, y_label: str, color: str) -> go.Figure:
        fig = px.bar(df, x="monat", y=col,
                     labels={"monat": "Monat", col: y_label},
                     color_discrete_sequence=[color],
                     text=col)
        fmt = "%{text:,.0f}" if col in ("total_trips", "total_revenue") else "%{text:.2f}"
        fig.update_traces(
            texttemplate=fmt, textposition="outside",
            marker_line_color=COLORS["border"], marker_line_width=1,
        )
        fig.update_layout(**self._layout(
            xaxis={"type": "category"},
            yaxis={"title": y_label},
        ))
        return fig


# ══════════════════════════════════════════════════════════════════════════════
# 3. Dashboard – TaxiDashboard
# ══════════════════════════════════════════════════════════════════════════════

class TaxiDashboard:
    """Orchestriert die Streamlit-Oberfläche."""

    def __init__(self) -> None:
        st.set_page_config(
            page_title="NYC Taxi Übersicht",
            page_icon="🚕",
            layout="wide",
        )
        self._charts = ChartBuilder()
        self._filters = self._render_sidebar()
        self._repo = TaxiDataRepository(
            dataset=self._filters["dataset"],
            max_dist=self._filters["max_dist"],
            min_fare=self._filters["min_fare"],
            file_yellow=self._filters["file_yellow"],
            file_green=self._filters["file_green"],
            month=self._filters["month"],
        )

    # ── Sidebar ────────────────────────────────────────────────────────────────

    @staticmethod
    def _render_sidebar() -> dict:
        available = _get_available_months()
        with st.sidebar:
            st.header("Filter")
            month    = st.selectbox("Monat", available, index=len(available) - 1 if available else 0)
            dataset  = st.selectbox("Datensatz", ["Yellow Taxi", "Green Taxi", "Beide"])
            max_dist = st.slider("Maximale Fahrstrecke (Meilen)", 1, 100, 50)
            min_fare = st.number_input("Mindestfahrpreis ($)", min_value=0.0, value=0.0, step=1.0)
            st.markdown("---")
            fy = os.path.join(DATA_DIR, f"yellow_tripdata_{month}.parquet")
            fg = os.path.join(DATA_DIR, f"green_tripdata_{month}.parquet")
            cy = _fmt_count(_count_trips(fy))
            cg = _fmt_count(_count_trips(fg))
            st.markdown(
                f"🟡 Yellow &nbsp;<b>{cy} Fahrten</b><br>"
                f"🟢 Green &nbsp;&nbsp;<b>{cg} Fahrten</b>",
                unsafe_allow_html=True,
            )
        return {
            "month":       month,
            "dataset":     dataset,
            "max_dist":    max_dist,
            "min_fare":    min_fare,
            "file_yellow": os.path.join(DATA_DIR, f"yellow_tripdata_{month}.parquet"),
            "file_green":  os.path.join(DATA_DIR, f"green_tripdata_{month}.parquet"),
        }

    # ── Abschnitte ─────────────────────────────────────────────────────────────

    def _section_header(self) -> None:
        st.title(f"🚕 NYC Taxi Daten – {self._filters['month']}")
        st.caption("Datenquelle: NYC TLC Trip Record Data | Verarbeitung: DuckDB + Streamlit")

    def _section_kpis(self) -> None:
        kpi = self._repo.get_kpis()
        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("Fahrten gesamt",      f"{int(kpi.total_trips):,}".replace(",", "."))
        c2.metric("Gesamtumsatz",        f"${kpi.total_revenue:,.0f}".replace(",", "."))
        c3.metric("Ø Fahrpreis",         f"${kpi.avg_fare:.2f}")
        c4.metric("Ø Distanz (Meilen)",  f"{kpi.avg_distance:.2f}")
        c5.metric("Ø Trinkgeld",         f"${kpi.avg_tip:.2f}")
        st.markdown("---")

    def _section_time(self) -> None:
        col_l, col_r = st.columns(2)
        with col_l:
            st.subheader("📅 Fahrten pro Tag")
            st.plotly_chart(
                self._charts.daily_trips(self._repo.get_daily_trips()),
                width='stretch',
            )
        with col_r:
            st.subheader("🕐 Fahrten nach Uhrzeit")
            st.plotly_chart(
                self._charts.hourly_trips(self._repo.get_hourly_trips()),
                width='stretch',
            )

    def _section_payment_distance(self) -> None:
        col_l, col_r = st.columns(2)
        with col_l:
            st.subheader("💳 Zahlungsarten")
            st.plotly_chart(
                self._charts.payment_pie(self._repo.get_payment_distribution()),
                width='stretch',
            )
        with col_r:
            st.subheader("📏 Fahrstrecken-Verteilung")
            st.plotly_chart(
                self._charts.distance_histogram(self._repo.get_distance_distribution()),
                width='stretch',
            )

    def _section_zones(self) -> None:
        col_l, col_r = st.columns(2)
        with col_l:
            st.subheader("📍 Top 15 Abholzonen")
            st.plotly_chart(
                self._charts.zone_bar(self._repo.get_top_pickup_zones()),
                width='stretch',
            )
        with col_r:
            st.subheader("🏁 Top 15 Zielzonen")
            st.plotly_chart(
                self._charts.zone_bar(self._repo.get_top_dropoff_zones()),
                width='stretch',
            )

    def _section_fare_passengers(self) -> None:
        col_l, col_r = st.columns(2)
        with col_l:
            st.subheader("💰 Durchschnittlicher Fahrpreis pro Stunde")
            st.plotly_chart(
                self._charts.hourly_fare_line(self._repo.get_hourly_fare_tip()),
                width='stretch',
            )
        with col_r:
            st.subheader("👥 Passagieranzahl-Verteilung")
            st.plotly_chart(
                self._charts.passenger_bar(self._repo.get_passenger_distribution()),
                width='stretch',
            )

    def _section_weekday(self) -> None:
        st.subheader("📆 Fahrten nach Wochentag")
        weekday_df = self._repo.get_weekday_stats()
        col_l, col_r = st.columns(2)
        with col_l:
            st.plotly_chart(
                self._charts.weekday_trips(weekday_df),
                width='stretch',
            )
        with col_r:
            st.plotly_chart(
                self._charts.weekday_fare(weekday_df),
                width='stretch',
            )

    def _section_monthly_trends(self) -> None:
        st.markdown("---")
        st.subheader("📈 Monatsvergleich")
        mdf = _get_monthly_kpis(self._filters["dataset"], tuple(_get_available_months()))
        if mdf.empty or len(mdf) < 2:
            st.info("Für den Monatsvergleich werden mindestens 2 Monate benötigt.")
            return
        col_l, col_r = st.columns(2)
        with col_l:
            st.caption("🚖 Fahrten gesamt")
            st.plotly_chart(
                self._charts.monthly_kpi_bar(mdf, "total_trips", "Fahrten", COLORS["primary"]),
                width="stretch")
        with col_r:
            st.caption("💵 Gesamtumsatz ($)")
            st.plotly_chart(
                self._charts.monthly_kpi_bar(mdf, "total_revenue", "Umsatz ($)", COLORS["secondary"]),
                width="stretch")
        col_l, col_r = st.columns(2)
        with col_l:
            st.caption("💲 Ø Fahrpreis ($)")
            st.plotly_chart(
                self._charts.monthly_kpi_bar(mdf, "avg_fare", "Ø Fahrpreis ($)", COLORS["accent"]),
                width="stretch")
        with col_r:
            st.caption("🛣️ Ø Distanz (Meilen)")
            st.plotly_chart(
                self._charts.monthly_kpi_bar(mdf, "avg_distance", "Ø Distanz (Meilen)", COLORS["dark"]),
                width="stretch")
        col_l, col_r = st.columns(2)
        with col_l:
            st.caption("💰 Ø Trinkgeld ($)")
            st.plotly_chart(
                self._charts.monthly_kpi_bar(mdf, "avg_tip", "Ø Trinkgeld ($)", COLORS["primary"]),
                width="stretch")

    def _section_raw_data(self) -> None:
        st.markdown("---")
        st.subheader("🗂️ Rohdaten – erste 30 Einträge")
        df = self._repo.get_raw_data(30)
        st.dataframe(df, use_container_width=True, hide_index=True)

    def _section_footer(self) -> None:
        st.markdown("---")
        st.caption(f"Erstellt mit Streamlit · DuckDB · Plotly | NYC TLC Daten {self._filters['month']}")

    # ── Einstiegspunkt ─────────────────────────────────────────────────────────

    def run(self) -> None:
        self._section_header()
        self._section_kpis()
        self._section_time()
        self._section_payment_distance()
        self._section_zones()
        self._section_fare_passengers()
        self._section_weekday()
        self._section_monthly_trends()
        self._section_raw_data()
        self._section_footer()


# ══════════════════════════════════════════════════════════════════════════════
# Start
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__" or True:
    TaxiDashboard().run()


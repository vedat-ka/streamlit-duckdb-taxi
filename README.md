# 🚕 NYC Taxi Übersicht – Streamlit + DuckDB

Interaktives Dashboard zur Auswertung der NYC TLC Taxi-Fahrtdaten (Januar 2026).  
Verarbeitung direkt auf Parquet-Dateien mit **DuckDB**, Visualisierung mit **Plotly** und **Streamlit**.

---

## Projektstruktur

```
streamlit-duckbd-taxi/
├── app.py                   # Streamlit-Hauptanwendung
├── requirements.txt         # Python-Abhängigkeiten
├── .gitignore
├── README.md
├── db/                      # Datenbankpaket
│   ├── __init__.py
│   ├── connection.py        # DuckDB-Verbindung & Views
│   ├── queries.py           # SQL-Abfragen
│   └── sources.py           # FROM-Klausel & WHERE-Filter
└── data/                    # Parquet-Dateien (nicht im Repo, s. .gitignore)
    ├── yellow_tripdata_YYYY-MM.parquet
    ├── green_tripdata_YYYY-MM.parquet
    └── .gitkeep
```

---

## Voraussetzungen

- Python **3.10** oder neuer
- `pip` und `venv` (in der Standardbibliothek enthalten)

---

## Setup – Virtuelle Umgebung

```bash
# 1. Ins Projektverzeichnis wechseln
cd streamlit-duckbd-taxi

# 2. Virtuelle Umgebung erstellen
python3 -m venv .venv

# 3. Virtuelle Umgebung aktivieren
#    Linux / macOS:
source .venv/bin/activate
#    Windows (PowerShell):
.venv\Scripts\Activate.ps1
#    Windows (CMD):
.venv\Scripts\activate.bat

# 4. Abhängigkeiten installieren
pip install -r requirements.txt
```

---

## App starten

```bash
streamlit run app.py
```

Die App öffnet sich automatisch im Browser unter **http://localhost:8501**

Optionale Parameter:

```bash
# Anderen Port verwenden
streamlit run app.py --server.port 8502

# Headless-Modus (kein automatisches Browser-Öffnen, z. B. auf Servern)
streamlit run app.py --server.headless true
```

---

## App stoppen

Im Terminal, in dem die App läuft:

```
Strg + C
```

Falls die App im Hintergrund läuft:

```bash
# Prozess-ID herausfinden
lsof -i :8501

# App beenden (PID ersetzen)
kill <PID>

# Oder alle Streamlit-Prozesse beenden
pkill -f "streamlit run"
```

---

## Dashboard-Inhalte

| Abschnitt | Beschreibung |
|---|---|
| **KPI-Zeile** | Fahrten gesamt, Gesamtumsatz, Ø Fahrpreis, Ø Distanz, Ø Trinkgeld |
| **Fahrten pro Tag** | Tägliche Fahrtenanzahl über den gesamten Januar |
| **Fahrten nach Uhrzeit** | Rush-Hour-Muster über 24 Stunden |
| **Zahlungsarten** | Anteil Kreditkarte, Bar und weitere |
| **Fahrstrecken-Verteilung** | Histogramm der Fahrstrecken in Meilen |
| **Top 15 Abholzonen** | Häufigste Startpunkte nach Zone und Borough |
| **Top 15 Zielzonen** | Häufigste Ziele nach Zone und Borough |
| **Ø Preis & Trinkgeld/h** | Durchschnittliche Beträge je Tagesstunde |
| **Passagieranzahl** | Verteilung 1–8 Personen pro Fahrt |
| **Wochentag-Analyse** | Fahrtenanzahl und Ø Preis nach Wochentag |

### Sidebar-Filter

- **Datensatz**: Yellow Taxi, Green Taxi oder beide
- **Maximale Fahrstrecke**: Slider 1–100 Meilen
- **Mindestfahrpreis**: Freitextfeld in Dollar

---

## Daten herunterladen

Die Parquet-Dateien sind **nicht im Repository enthalten** (zu groß, via `.gitignore` ausgeschlossen).  
Sie müssen manuell heruntergeladen und in den `data/`-Ordner abgelegt werden.

**Download:** [NYC Taxi & Limousine Commission (TLC) Trip Record Data](https://www.nyc.gov/site/tlc/about/tlc-trip-record-data.page)

Benötigte Dateien (Beispiel für Januar 2026):

```
data/
├── yellow_tripdata_2026-01.parquet
└── green_tripdata_2026-01.parquet
```

Die App erkennt automatisch alle verfügbaren Monate im `data/`-Ordner.  
Es können beliebig viele Monate (Yellow + Green) abgelegt werden.

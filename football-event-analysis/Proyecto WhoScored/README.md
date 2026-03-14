# Análisis de eventos de fútbol — WhoScored + FBRef

Pipeline de datos multifuente y toolkit de visualización para el análisis táctico de partidos de fútbol. Extrae datos de eventos detallados desde WhoScored y estadísticas de jugadores desde FBRef, y genera visualizaciones tácticas e informes post-partido.

Aplicado a la temporada de La Liga 2025–2026.

---

## ¿Qué hace?

1. **Extrae calendarios de partidos** desde WhoScored (partidos finalizados, resultados, IDs)
2. **Extrae datos del match center** — registro completo de eventos: pases, tiros, acciones defensivas, acciones de portero, formaciones, posiciones de jugadores y línea de tiempo del marcador
3. **Extrae estadísticas de jugadores** desde FBRef (top 5 ligas europeas)
4. **Normaliza** todos los datos en CSVs y JSONs estructurados por partido
5. **Genera visualizaciones** — gráficos de pizza, redes de pases, mapas de tiros, comparativas de jugadores

---

## Estructura del proyecto

```
├── src/
│   ├── whoscored_viz/
│   │   ├── whoscored_matchcenter.py  # Scraper del match center (1.200+ líneas)
│   │   ├── whoscored_fixtures.py     # Scraper de calendarios con Selenium
│   │   ├── dictionaries.py           # Construcción de diccionarios de equipos y jugadores
│   │   ├── identity.py               # Identidad visual de equipos (colores, escudos)
│   │   ├── paths.py                  # Configuración de rutas
│   │   └── utils_io.py               # Lectura de CSV con fallbacks de codificación
│   └── fbref_viz/
│       └── fbref_scraper.py          # Scraper de estadísticas FBRef (750+ líneas)
├── notebooks/
│   ├── 00_identidad.ipynb            # Construir diccionarios de equipos y jugadores
│   ├── 01_descarga_fixtures.ipynb    # Scraping de calendarios
│   ├── 02_descarga_matchcenter.ipynb # Scraping de datos del match center
│   ├── 03_ws_index_min.ipynb         # Construcción del índice de partidos
│   ├── 04_visualizaciones_whoscored.ipynb  # Visualizaciones desde WhoScored
│   ├── 05_visualizaciones_fbref.ipynb      # Visualizaciones desde FBRef
│   └── Reporte_Post_Partido.ipynb    # Generador de informes post-partido
├── data/
│   ├── dictionaries/                 # CSVs de referencia de equipos y jugadores
│   ├── processed/index/              # Índice de partidos con metadatos
│   └── raw/
│       ├── fixtures/                 # Calendarios (CSV + JSON)
│       ├── fbref/                    # Estadísticas de jugadores de FBRef
│       └── matchcenter/              # Datos de eventos por partido (no versionado)
├── assets/
│   └── viz/                          # Visualizaciones generadas
├── data_sample/                      # Filas de muestra de eventos (CSV)
├── requirements.txt
└── README.md
```

---

## Datos recopilados por partido

Cada partido scrapeado genera 11 archivos dentro de `data/raw/matchcenter/<carpeta_partido>/csv/`:

| Archivo | Descripción |
|---|---|
| `events.csv` | Todos los eventos del partido con tipo, minuto y coordenadas |
| `events_passes.csv` | Pases con receptor, éxito y origen/destino |
| `events_shots.csv` | Tiros con xG, xG2 y posición en portería |
| `events_defensive.csv` | Entradas, intercepciones, bloqueos, duelos aéreos, faltas |
| `events_gk_actions.csv` | Acciones del portero con datos de posición |
| `formations_timeline.csv` | Cambios de alineación a lo largo del partido |
| `formations_timeline_scored.csv` | Formaciones con posiciones de jugadores |
| `player_positions_timeline.csv` | Seguimiento de posición por jugador en el tiempo |
| `match_meta.csv` | Equipos, resultado, fecha, árbitro, asistencia |
| `players.csv` | Lista completa de convocados con posiciones y dorsales |
| `score_timeline.csv` | Eventos de gol con goleador y asistente |

---

## Instalación

```bash
# 1. Crear entorno virtual
python -m venv .venv
.venv\Scripts\activate   # Windows
source .venv/bin/activate  # Linux/macOS

# 2. Instalar dependencias
pip install -r requirements.txt

# 3. Configurar directorio de datos
# Crear un archivo .env en la raíz del proyecto:
echo "BASE_DATA_DIR=C:\ruta\a\tus\datos" > .env
```

> Los scrapers con Selenium requieren Google Chrome instalado. `undetected-chromedriver` gestiona el driver automáticamente.

---

## Uso

### Scraping de calendarios

```python
# notebooks/01_descarga_fixtures.ipynb
# O desde Python:
from src.whoscored_viz.whoscored_fixtures import scrape_range_finished
scrape_range_finished(comp="laliga", season="2025-2026", start="2025-08", end="2026-05")
```

### Scraping del match center

```bash
# Un partido por URL
python -m src.whoscored_viz.whoscored_matchcenter --url "https://www.whoscored.com/Matches/..."

# Procesamiento en lote desde CSV de fixtures
python -m src.whoscored_viz.whoscored_matchcenter --from-csv data/raw/fixtures/DataFixtures/laliga/2025-2026/finished_matches.csv
```

### Scraping de estadísticas FBRef

```python
from src.fbref_viz.fbref_scraper import main
main()  # Guarda jugadores_campo_2025_2026.csv y porteros_2025_2026.csv
```

---

## Decisiones técnicas clave

- **Selenium + undetected-chromedriver** — WhoScored renderiza los datos en el cliente mediante JavaScript; se necesita un navegador real para extraer el payload JSON embebido
- **Extracción del payload embebido** — los datos del partido están almacenados en una variable JavaScript dentro del HTML; el scraper extrae y parsea este payload directamente en lugar de raspar el DOM elemento a elemento
- **Almacenamiento idempotente de fixtures** — `append_dedup_csv()` deduplica por ID de partido antes de añadir, haciendo seguras las re-ejecuciones
- **Sistema de identidad visual de equipos** — `identity.py` mapea IDs de equipo a colores primarios/secundarios y rutas de escudos, usado de forma consistente en todas las visualizaciones
- **Tablas ocultas en comentarios de FBRef** — FBRef embebe algunas tablas de estadísticas dentro de comentarios HTML; `extract_table_html()` gestiona tanto las secciones visibles como las ocultas en comentarios

---

## Datos de muestra

La carpeta `data_sample/` contiene filas representativas de un partido real (Girona vs Rayo Vallecano, 15 ago 2025) para inspección rápida sin necesidad de ejecutar los scrapers.

---

## Stack tecnológico

| Categoría | Herramientas |
|---|---|
| Lenguaje | Python 3.11+ |
| Automatización de navegador | `selenium`, `undetected-chromedriver` |
| Parseo HTML | `BeautifulSoup4` |
| HTTP | `requests` |
| Procesamiento de datos | `pandas`, `numpy` |
| Visualización | `mplsoccer`, `matplotlib`, `Pillow` |
| Análisis | `scikit-learn`, `networkx` |
| Almacenamiento | CSV, JSON, Parquet |

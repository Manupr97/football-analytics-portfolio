# Pipeline de datos de fútbol — Segunda RFEF Grupo 3

Pipeline ETL automatizado que extrae datos de partidos desde BeSoccer, parsea el HTML y construye un modelo dimensional listo para análisis en Power BI.

Desarrollado para el seguimiento de la temporada del CE Sant Andreu en la Segunda División RFEF (Grupo 3), cubriendo partidos, alineaciones, goles, sustituciones y eventos de videoanalisis.

---

## ¿Qué hace?

1. **Extrae** clasificación, calendarios, alineaciones y eventos de partido desde BeSoccer
2. **Parsea** el HTML en objetos de datos estructurados
3. **Transforma** los datos en un modelo dimensional (dimensiones + tablas de hechos)
4. **Exporta** archivos Parquet listos para cargar en Power BI

El pipeline funciona de forma incremental: registra qué partidos ya han sido procesados y solo extrae los nuevos.

---

## Estructura del proyecto

```
├── src/
│   ├── config.py               # Configuración centralizada (rutas, URLs, timeouts)
│   ├── scrapers/               # Capa de descarga HTTP
│   │   ├── classification.py   # Clasificación → lista de equipos
│   │   ├── matches.py          # Calendario de partidos por equipo
│   │   ├── events.py           # Eventos de partido (goles, sustituciones) con caché HTML
│   │   └── lineups.py          # Alineaciones con caché HTML
│   ├── parsers/                # HTML → objetos de datos
│   │   ├── event_parser.py     # Goles y sustituciones
│   │   └── lineup_parser.py    # Apariciones y posiciones de jugadores
│   ├── transform/              # Objetos → DataFrames → Parquet
│   │   ├── dim_equipos.py
│   │   ├── dim_jugadores.py
│   │   ├── dim_partidos.py
│   │   ├── fact_appearances.py
│   │   ├── fact_goals.py
│   │   └── fact_substitutions.py
│   ├── pipeline/               # Orquestación
│   │   ├── run_pipeline.py     # Punto de entrada principal
│   │   └── processed_matches.py  # Registro de partidos procesados
│   └── utils/
│       ├── http_client.py      # Sesión HTTP con reintentos y control de velocidad
│       ├── parquet_utils.py    # Lógica de upsert en Parquet
│       ├── player_utils.py     # Generación de claves sustitutas estables
│       ├── logging_config.py   # Configuración de logs (archivo + consola)
│       └── cleanup_html.py     # CLI para gestión de caché HTML
├── notebooks/
│   ├── Scraping_Besoccer_2RFEF_G3.ipynb   # Demo completo del pipeline de scraping
│   └── Extracción_Videoanalisis.ipynb     # Extracción de datos de videoanalisis
├── data_sample/                # Filas de muestra de cada tabla (CSV)
├── assets/                     # Capturas del dashboard Power BI
├── requirements.txt
└── README.md
```

---

## Modelo de datos

Esquema en estrella con 3 tablas de dimensiones y 3 tablas de hechos:

| Tabla | Filas (aprox.) | Descripción |
|---|---|---|
| `dim_equipos` | 18 | Equipos del grupo |
| `dim_jugadores` | 594 | Todos los jugadores vistos en la temporada |
| `dim_partidos` | 306 | Partidos (finalizados y programados) |
| `fact_goals` | 554 | Goles con goleador, asistente, minuto y tipo |
| `fact_appearances` | 9.104 | Apariciones de jugadores por partido |
| `fact_substitutions` | 2.086 | Eventos de sustitución |

Todas las tablas usan `match_id` como clave principal de unión. Los jugadores usan una clave sustituta estable (`player_sk`) generada a partir del ID de BeSoccer cuando está disponible, o mediante un hash normalizado de (nombre + equipo).

---

## Instalación

```bash
# 1. Crear entorno virtual
python -m venv .venv
.venv\Scripts\activate   # Windows
source .venv/bin/activate  # Linux/macOS

# 2. Instalar dependencias
pip install -r requirements.txt

# 3. Configurar directorio del proyecto (opcional)
set SANT_ANDREU_PROJECT_DIR=C:\ruta\al\proyecto   # Windows
export SANT_ANDREU_PROJECT_DIR=/ruta/al/proyecto  # Linux/macOS
```

---

## Uso

```python
from src.pipeline.run_pipeline import run_incremental, run_full_reprocess

# Procesar solo partidos nuevos (recomendado para actualizaciones periódicas)
stats = run_incremental()

# Reprocesar todos los partidos desde el caché HTML
stats = run_full_reprocess()

print(stats)
```

---

## Decisiones técnicas clave

- **Caché HTML** — las páginas descargadas se guardan en `html/` antes de parsearlas, permitiendo reprocesar offline y auditar sin volver a hacer scraping
- **Procesamiento incremental** — `processed_matches.parquet` registra qué `match_id` ya han sido ingestados; las re-ejecuciones son seguras e idempotentes
- **Upserts en Parquet** — lógica personalizada que elimina registros antiguos por clave compuesta antes de añadir los nuevos, manteniendo los archivos consistentes
- **Claves sustitutas estables** — los jugadores sin ID de BeSoccer reciben una clave negativa determinista basada en el hash normalizado de (nombre + equipo), garantizando que el mismo jugador siempre tenga la misma SK en todas las tablas de hechos
- **Control de velocidad** — delays aleatorios configurables (1–3 segundos) entre peticiones para evitar bloqueos

---

## Datos de muestra

La carpeta `data_sample/` contiene filas representativas de cada tabla en formato CSV para inspección rápida sin necesidad de ejecutar el pipeline.

---

## Stack tecnológico

| Categoría | Herramientas |
|---|---|
| Lenguaje | Python 3.11+ |
| HTTP | `requests` + reintentos con backoff |
| Parseo HTML | `BeautifulSoup4` + `lxml` |
| Procesamiento de datos | `pandas`, `numpy` |
| Almacenamiento | Apache Parquet via `pyarrow` |
| Salida BI | Power BI (conector Parquet) |

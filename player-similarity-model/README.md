# Modelo de similitud de jugadores ofensivos — Top 5 Ligas Europeas

Herramienta de análisis exploratorio que identifica jugadores con perfiles estadísticos similares a partir de datos de FBRef y eventos de WhoScored. Diseñada para apoyar tareas de scouting, comparativa de perfiles y análisis táctico en ligas de élite.

> **Estado actual:** v2 activa — 32 features, 121 jugadores ofensivos, temporada 2025-26.

---

## Problema que aborda

Comparar jugadores entre ligas es difícil por el ruido de las métricas de volumen: un extremo que juega en un equipo dominante acumula más toques, pases y ocasiones que uno en un equipo inferior, aunque su perfil de juego sea el mismo. Este proyecto construye una representación normalizada del estilo de cada jugador que permite comparaciones más justas entre contextos distintos.

El objetivo no es sustituir el criterio del analista, sino ofrecer una primera capa exploratoria de similitud táctica que ayude a priorizar jugadores para un análisis más profundo.

---

## Metodología

### 1. Selección de jugadores

- Fuente: FBRef Big 5 Leagues, temporada 2025-26
- Filtro de posición: jugadores con `FW` en su posición registrada (delanteros puros, extremos, perfiles mixtos FW/MF)
- Filtro de minutos: mínimo 450 minutos jugados (~5 partidos completos)
- Resultado: **121 jugadores** en 5 ligas

### 2. Feature engineering

Las features se organizan en tres bloques que responden a preguntas distintas sobre el perfil de cada jugador. Esta separación conceptual es estándar en football analytics y facilita interpretar qué dimensión del juego impulsa cada similitud.

**Volume metrics (12 features) — ¿cuánto participa el jugador?**
Métricas brutas normalizadas per-90: goles, asistencias, xG, xA, tiros, toques, toques en área rival, conducciones progresivas, regates completados, faltas recibidas, centros y duelos aéreos totales.
Capturan la intensidad de participación ofensiva: un delantero con alta carga de trabajo frente a uno con rol más intermitente, aunque ambos sean eficientes.

**Efficiency metrics — ¿qué calidad tienen sus acciones?**
Incluidas parcialmente en los bloques FBRef (p.ej. xG por tiro implícito en la ratio tiros/xG) y explicitadas en las features de WhoScored: `shot_zone_box_pct` mide si el delantero genera sus tiros desde posiciones de alta probabilidad.
Complementan las métricas de volumen: un mismo número de tiros per-90 tiene distinto valor según la zona desde la que se producen.

**Style metrics (17 features) — ¿cómo juega el jugador?**
Ratios y porcentajes independientes del volumen absoluto: precisión de tiro, distancia media de tiro, éxito en regates, precisión de pase, distribución por longitud del pase, ratio de pases progresivos, ratio al tercio final, ratio al área, ratio de throughballs, % de toques en zona ofensiva, ratio de conducciones progresivas, % de duelos aéreos ganados, ratio creación/finalización, `pct_passes_forward` y `avg_pass_length`.
Son las features más robustas para comparar jugadores entre equipos o ligas distintas, porque no dependen del volumen de posesión del equipo.

### 3. Consideraciones sobre la normalización per-90

Las métricas de volumen se expresan per-90 minutos, lo que elimina el efecto del tiempo jugado, pero **no el del contexto de equipo**. Un extremo en un equipo de alta posesión acumula más toques, pases y ocasiones per-90 que uno en un equipo de repliegue, aunque su perfil táctico sea idéntico. Esta limitación es inherente a cualquier métrica de volumen y no se resuelve completamente con la normalización por minutos.

Para mitigar este sesgo el modelo aplica dos mecanismos complementarios:

- **StandardScaler global**: transforma cada feature a media 0 y desviación típica 1 sobre el conjunto completo de jugadores. Esto hace que las diferencias en el espacio escalado reflejen desviaciones relativas respecto al conjunto, reduciendo el peso de los outliers de volumen asociados a equipos dominantes.
- **Peso proporcional de los bloques**: al incluir 17 features de estilo frente a 12 de volumen, el vector de cada jugador está dominado por métricas más independientes del contexto de equipo. La similitud coseno operará principalmente sobre la dirección que definen estas features de estilo.

En versiones futuras se evaluará una normalización por liga o por quintil de posesión del equipo para corregir este sesgo de forma más explícita (véase *Próximos pasos*).

### 4. Auditoría y reducción de features

Antes de construir el modelo se realizó una auditoría completa del espacio de features:

- Se calculó la matriz de correlación entre todas las features candidatas
- Se eliminaron **9 features** con |r| > 0.8 respecto a otras ya incluidas (p.ej. `npxg_p90` correlaciona 0.875 con `xg_p90`)
- Se eliminó `edad` por tener varianza nula en el subconjunto filtrado
- El análisis PCA confirma que 2 componentes capturan solo el 41% de la varianza y se necesitan 11 para alcanzar el 80%, indicando que el espacio de features es genuinamente multidimensional y no reducible sin pérdida de información relevante

### 5. Enriquecimiento con eventos WhoScored (v2)

La v1 del modelo usaba únicamente estadísticas agregadas de FBRef. La v2 añade 3 features derivadas de los eventos partido a partido de WhoScored, extraídas de **1.189 partidos** de las 5 grandes ligas:

| Feature | Bloque | Descripción | Fuente |
|---|---|---|---|
| `pct_passes_forward` | Style | % de pases en dirección a portería rival (`end_x > x`) | `events_passes.parquet` |
| `avg_pass_length` | Style | Longitud media de pases completados (metros) | `events_passes.parquet` |
| `shot_zone_box_pct` | Efficiency | % de tiros originados dentro del área grande (`x > 83`) | `events_shots.parquet` |

Estas features capturan comportamiento táctico que FBRef no desglosa: la intencionalidad direccional de los pases, la preferencia por el pase largo o corto, y si el delantero busca el área o dispara desde fuera. Al ser ratios, pertenecen al bloque de estilo/eficiencia y son especialmente útiles para comparar jugadores entre ligas.

La unión entre FBRef y WhoScored se realiza por nombre normalizado. Los 5 casos con diferencia de nombre entre fuentes se resuelven con overrides explícitos y documentados en el código.

### 6. Normalización y escalado

Se aplica `StandardScaler` (media=0, desviación típica=1) a todos los bloques de features. Los valores NaN correspondientes al único jugador sin cobertura en WhoScored se imputan con la mediana de cada columna antes de escalar.

El StandardScaler es la elección correcta aquí por dos razones:
1. Las features tienen escalas muy distintas (p.ej. minutos vs. ratios entre 0 y 1): escalar a varianza unitaria elimina este efecto y evita que el modelo esté dominado por las features de mayor rango numérico.
2. Al centrar en media 0, la similitud coseno opera sobre desviaciones respecto a la media del conjunto, lo que equivale a comparar perfiles relativos en lugar de valores absolutos.

Los scalers se serializan con `joblib` para transformar nuevos jugadores sin reentrenar.

### 7. Modelo de similitud

Se calcula la **similitud coseno** entre el vector de features de cada jugador y el del resto. Formalmente, para dos jugadores con vectores **u** y **v**:

```
similitud(u, v) = (u · v) / (‖u‖ · ‖v‖)
```

La similitud coseno mide el ángulo entre dos vectores, no la distancia euclidiana entre ellos. Esto tiene una propiedad clave para este problema: **dos jugadores son similares si su perfil de juego apunta en la misma dirección**, independientemente de si uno juega en la Premier League y otro en la Ligue 1. Un jugador con todas sus métricas ligeramente más altas que otro (posiblemente por contexto de equipo) puede tener similitud alta, porque la orientación de su vector es parecida aunque su magnitud sea distinta.

Combinado con el StandardScaler, que ya ha corregido las diferencias de escala entre features, la similitud coseno es la medida más apropiada para comparar estilos de juego en un espacio heterogéneo y multidimensional.

Rango efectivo: [0, 1], donde 1 indica perfiles prácticamente idénticos y 0 indica perfiles ortogonales.

---

## Fuentes de datos

| Fuente | Datos | Cobertura |
|---|---|---|
| [FBRef](https://fbref.com) | Estadísticas acumuladas de temporada: estándar, tiro, pases, posesión, defensiva | Big 5 Leagues, 2025-26 |
| WhoScored (via scraper propio) | Eventos de partido: pases, tiros, acciones defensivas, alineaciones | 1.189 partidos, Big 5 Leagues, 2025-26 |

Los datos de FBRef se descargan mediante scraping del HTML público con `requests` + `BeautifulSoup`. Los datos de WhoScored se extraen mediante automatización de navegador con `Selenium`.

---

## Estructura del repositorio

```
player-similarity-model/
│
├── src/
│   ├── scraping/
│   │   └── fbref_scraper.py          # Descarga datos de FBRef (Big 5, jugadores de campo)
│   │
│   ├── features/
│   │   ├── load_fbref.py             # Carga, filtra y valida el dataset de FBRef
│   │   ├── volume_features.py        # Métricas de volumen per 90 (bloque B)
│   │   ├── style_features.py         # Métricas de estilo, ratios y porcentajes (bloque C)
│   │   └── whoscored_features.py     # Agregación de eventos WhoScored por jugador
│   │
│   ├── preprocessing/
│   │   └── normalize_features.py     # Imputación de NaN + StandardScaler
│   │
│   ├── models/
│   │   └── similarity_model.py       # PlayerSimilarityModel — cosine similarity
│   │
│   ├── pipeline/
│   │   ├── build_whoscored_features_phase1.py  # Merge FBRef + WhoScored
│   │   └── build_model.py            # Orquestador + CLI
│   │
│   ├── utils/
│   │   └── feature_config.py         # Lista de features v1 y v2, bloques, columnas ID
│   │
│   └── build_features_base.py        # Pipeline base (FBRef only)
│
├── data/
│   ├── raw/fbref/                    # CSVs descargados de FBRef (gitignored)
│   └── features/
│       ├── features_base_mvp.parquet        # Dataset base auditado (FBRef, sin normalizar)
│       ├── features_model.parquet           # Modelo v1 normalizado (29 features)
│       ├── features_model_v2_phase1.parquet # Dataset enriquecido antes de normalizar
│       ├── features_model_v2.parquet        # Modelo v2 normalizado (32 features)
│       └── audit/                           # Heatmaps, distribuciones, PCA exploratorio
│
├── models/
│   └── scalers/
│       ├── feature_scaler.joblib     # Scaler v1
│       └── feature_scaler_v2.joblib  # Scaler v2
│
├── requirements.txt
└── README.md
```

---

## Instalación y ejecución

```bash
# 1. Clonar el repositorio y crear entorno virtual
git clone <repo-url>
cd player-similarity-model
python -m venv .venv
.venv\Scripts\activate   # Windows
source .venv/bin/activate  # Linux/macOS

# 2. Instalar dependencias
pip install -r requirements.txt
```

### Pipeline completo (desde cero)

```bash
# Paso 1 — Descargar datos de FBRef
python src/scraping/fbref_scraper.py

# Paso 2 — Construir dataset base con features FBRef
python src/build_features_base.py

# Paso 3 — Enriquecer con eventos WhoScored (requiere acceso a ws-analytics-platform)
python src/pipeline/build_whoscored_features_phase1.py --ws-dir /ruta/ws-analytics-platform

# Paso 4 — Normalizar y construir el modelo v2
python src/pipeline/build_model.py --build

# Paso 5 — Consultar similitudes
python src/pipeline/build_model.py --player "Vinicius" --top 10
```

### Si ya tienes los datasets generados

```bash
# Construir solo el modelo (sin re-scrapear)
python src/pipeline/build_model.py --build

# Consultar
python src/pipeline/build_model.py --player "Haaland" --top 8
python src/pipeline/build_model.py --player "Kane" --top 10 --exclude-same-team
python src/pipeline/build_model.py --player "Mbapp" --v1   # comparar contra v1
```

---

## Ejemplos de consulta

```bash
# Perfiles similares a Vinicius Júnior
python src/pipeline/build_model.py --player "Vinicius" --top 10

player_name                team                   competition        pos       min  similarity
----------------------------------------------------------------------------------------------
Nicolas Pépé               Villarreal             La Liga            FW,MF     536  0.8240
Michael Olise              Bayern Munich          Bundesliga         FW,MF     466  0.7760
Marcus Rashford            Barcelona              La Liga            FW        464  0.7690
Jack Grealish              Everton                Premier League     FW        556  0.7550
Kylian Mbappé              Real Madrid            La Liga            FW        696  0.6820

# Perfiles similares a Erling Haaland
python src/pipeline/build_model.py --player "Haaland" --top 8

player_name                team                   competition        pos       min  similarity
----------------------------------------------------------------------------------------------
Fisnik Asllani             Augsburg               Bundesliga         FW        ...  0.6870
Ferrán Torres              Barcelona              La Liga            FW        532  0.6050
Frank Magri                Lens                   Ligue 1            FW        ...  0.5890
Richarlison                Tottenham              Premier League     FW        ...  0.5660
```

---

## Hallazgos principales

### La v2 mejora la coherencia táctica

La incorporación de las features de WhoScored produce cambios pequeños pero tácticamente relevantes en los resultados. El caso más ilustrativo es la comparación entre Harry Kane y Erling Haaland.

**En v1** (solo FBRef): Kane aparecía como el segundo perfil más similar a Haaland (similitud 0.614).

**En v2** (FBRef + WhoScored): Kane baja a la posición 6 (similitud 0.544). La diferencia se explica por las nuevas features:
- `avg_pass_length` de Kane: **22.9 metros** (el más alto del dataset, perfil de pivote que combina largo)
- `avg_pass_length` de Haaland: **14.4 metros** (combinaciones cortas en el área)
- `shot_zone_box_pct` de Kane: **0.80** (mayoritariamente dentro del área, pero con más variedad)
- `shot_zone_box_pct` de Haaland: **0.89** (casi exclusivamente dentro del área)

Kane es un delantero de área que además actúa como punto de apoyo con el juego de espaldas y pase largo. Haaland es un rematador puro con muy poca participación en la construcción. FBRef ya capturaba parte de esta diferencia, pero las features de evento la hacen más explícita.

### El espacio de features es genuinamente multidimensional

El análisis PCA muestra que solo el 41% de la varianza queda recogida en 2 dimensiones, y se necesitan 11 componentes para alcanzar el 80%. Esto confirma que el perfil ofensivo de un jugador no se reduce a unos pocos ejes y que el modelo se beneficia de trabajar en el espacio completo de 32 features.

### Las ligas introducen sesgo en algunas métricas

Las métricas de goles y asistencias varían significativamente entre ligas (CV entre 0.28 y 0.44). La Bundesliga produce los valores más altos en el subconjunto analizado; la Serie A los más bajos. La normalización global con StandardScaler mitiga parcialmente este efecto, aunque en versiones futuras se evaluará una normalización por liga.

---

## Limitaciones

- **Cobertura de jugadores**: el filtro de 450 minutos excluye jugadores recién llegados, lesionados o con pocas apariciones, que pueden tener perfiles interesantes para scouting.
- **Una sola temporada**: el modelo captura el perfil actual (2025-26). No detecta cambios de rol entre temporadas ni trayectorias de desarrollo.
- **Join FBRef–WhoScored por nombre**: la unión entre las dos fuentes se hace por nombre normalizado, no por ID. Funciona para el 99.2% del dataset, pero es un punto frágil si los nombres difieren sustancialmente entre fuentes.
- **Sin contexto táctico del equipo**: dos jugadores con el mismo perfil estadístico pueden desempeñar roles distintos dependiendo del sistema de su equipo. El modelo no modela el contexto colectivo.
- **Porteros y laterales excluidos**: el modelo actual cubre únicamente perfiles ofensivos (FW y mixtos).

---

## Próximos pasos

- **Fase 2 de enriquecimiento WhoScored**: añadir `high_turnover_pct` (pressing en campo rival) y `tactical_position_vertical` (profundidad táctica media en la formación).
- **Normalización por liga**: evaluar si el z-score por liga mejora la comparabilidad entre competiciones.
- **Extensión a más posiciones**: aplicar el mismo pipeline a mediocampistas y defensas.
- **Interfaz web**: despliegue como aplicación Streamlit para consultas interactivas sin necesidad de CLI.
- **Validación cualitativa**: contraste de los resultados con criterios de scouting real para evaluar la utilidad práctica del modelo.

---

## Stack tecnológico

| Categoría | Herramientas |
|---|---|
| Lenguaje | Python 3.11+ |
| Scraping FBRef | `requests`, `BeautifulSoup4`, `lxml` |
| Procesamiento de datos | `pandas`, `numpy` |
| Modelo | `scikit-learn` (StandardScaler, cosine_similarity) |
| Serialización | `pyarrow` (Parquet), `joblib` |
| Análisis exploratorio | `matplotlib`, `seaborn` |

---

## Sobre el proyecto

Este proyecto forma parte de un portfolio de análisis de datos aplicado al fútbol. Se ha construido con datos reales de la temporada 2025-26 de las cinco grandes ligas europeas y refleja un flujo de trabajo completo: desde la adquisición de datos hasta el modelo de inferencia, pasando por auditoría de features y validación táctica de resultados.

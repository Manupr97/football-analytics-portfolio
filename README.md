# Football Analytics Portfolio

Portfolio de proyectos de análisis de datos aplicados al scouting y al análisis táctico en fútbol.

---

## Proyectos

### [Pipeline de datos de fútbol](./football-data-pipeline/Proyecto Sant Andreu/)
Pipeline ETL automatizado que extrae datos de partidos desde BeSoccer, parsea el HTML y construye un modelo dimensional listo para análisis en Power BI. Desarrollado para el seguimiento del UE Sant Andreu en la Segunda RFEF Grupo 3.

Extrae clasificación, calendarios, alineaciones y eventos de partido. Transforma los datos en un modelo dimensional con dimensiones y tablas de hechos, y exporta archivos Parquet de forma incremental.

`Python` `Pandas` `BeautifulSoup` `PyArrow` `Power BI`

---

### [Análisis de eventos de fútbol](./football-event-analysis/Proyecto WhoScored/)
Pipeline multifuente y toolkit de visualización para el análisis táctico de partidos. Extrae datos de eventos detallados desde WhoScored y estadísticas de jugadores desde FBRef, y genera visualizaciones tácticas e informes post-partido.

Aplicado a La Liga 2025–2026. Incluye redes de pases, mapas de tiros, gráficos de pizza de estilo de jugador y un notebook de informe post-partido.

`Python` `Pandas` `Selenium` `mplsoccer` `Matplotlib` `NetworkX` `scikit-learn`

---

### [Modelo de similitud de jugadores](./player-similarity-model/)
Herramienta de análisis exploratorio que identifica jugadores con perfiles estadísticos similares a partir de datos de FBRef y WhoScored. Construye una representación normalizada del estilo de cada jugador (32 features, 121 jugadores ofensivos) que permite comparaciones más justas entre ligas y contextos distintos.

Diseñada para apoyar tareas de scouting y comparativa de perfiles en las Top 5 ligas europeas, temporada 2025–2026.

`Python` `scikit-learn` `Pandas` `Selenium` `PyYAML`

---

### [Scouting CRM — Case Study](./scouting-crm-case-study/)
Documentación técnica de una plataforma interna de scouting desarrollada para el Club Atlético Central (Tercera Federación, Grupo 10). La aplicación digitaliza y estandariza el proceso de evaluación de jugadores: informes estructurados por posición, sincronización offline-first y pipeline de captación con consenso ponderado entre scouts.

El código es privado. Este case study documenta la arquitectura, las decisiones técnicas y el flujo de trabajo.

`Next.js` `React` `TypeScript` `Supabase` `Dexie` `PostgreSQL`

---

## Tecnologías

Python · Pandas · NumPy · scikit-learn · Selenium · BeautifulSoup · mplsoccer · Matplotlib · NetworkX · PyArrow · Next.js · React · TypeScript · Supabase · PostgreSQL · Dexie · Power BI

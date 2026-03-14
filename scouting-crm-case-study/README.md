# CAC Scouting CRM — Case Study

> Plataforma interna de scouting desarrollada para un club de fútbol semiprofesional con el objetivo de digitalizar y estandarizar el proceso de evaluación de jugadores.

---

## El problema

Los clubes semiprofesionales operan sus procesos de scouting de forma mayoritariamente informal: los scouts toman notas en papel o en hojas de cálculo personales, los criterios de evaluación varían entre personas y no existe un sistema compartido para agregar observaciones ni hacer seguimiento de jugadores a lo largo del tiempo.

Esto genera una serie de problemas recurrentes:

- **Evaluaciones inconsistentes.** Dos scouts que observan al mismo jugador pueden usar criterios distintos y producir informes incomparables.
- **Pérdida de contexto.** El historial de un jugador queda disperso en archivos personales. Cuando un scout abandona el club o un jugador reaparece meses después, recuperar las observaciones anteriores es difícil o imposible.
- **Sin soporte a la toma de decisiones.** El responsable de scouting no tiene una visión estructurada del conjunto de jugadores observados. Las decisiones de fichaje se toman de memoria o a partir de conversaciones informales, no a partir de datos agregados.
- **Restricciones de conectividad.** Los scouts trabajan en estadios y campos de entrenamiento con WiFi irregular o inexistente. Una herramienta puramente en la nube que requiera conexión constante no es viable sobre el terreno.

---

## Contexto: el scouting en el Club Atlético Central

El Club Atlético Central compite en la **Tercera Federación, Grupo 10** — una categoría nacional del fútbol semiprofesional español. El departamento de scouting del club cuenta con varios scouts que cubren distintas áreas geográficas, todos coordinados por un responsable de scouting encargado de identificar objetivos y elevar recomendaciones de fichaje al cuerpo técnico.

El club necesitaba una herramienta que:

1. Pudiera usarse desde un móvil en el estadio, con o sin internet.
2. Aplicara criterios de evaluación consensuados con el cuerpo técnico de forma uniforme.
3. Agregara los informes de varios scouts en un perfil de jugador unificado.
4. Ofreciera al responsable de scouting una visión clara del pipeline para priorizar las acciones de captación.

---

## La solución

Una **Progressive Web App (PWA)** construida específicamente para el flujo de trabajo del club. El sistema funciona completamente sin conexión: los scouts redactan informes en el estadio y los datos se sincronizan automáticamente con la nube cuando se recupera la conectividad. El responsable accede a los mismos datos desde cualquier navegador con una vista estructurada y agregada.

La plataforma es privada, de uso interno del club y no está distribuida públicamente.

---

## Funcionalidades principales

### Registro de jugadores
Base de datos centralizada de jugadores observados, cada uno con un perfil que incluye datos personales, posición, equipo actual y estado de captación. Los jugadores nunca se eliminan definitivamente: su historial se preserva siempre.

### Informes de scouting estructurados
Los scouts completan un formulario de evaluación adaptado a la posición del jugador, con métricas consensuadas con el cuerpo técnico. Cada métrica se puntúa en una escala del 1 al 10 con anclas definidas (qué significa un 4, un 6, un 8 y un 10 en la práctica). Las métricas se agrupan en cuatro dimensiones: técnica, táctica, física y mental.

### Puntuación ponderada y consenso automático
Las métricas prioritarias — aquellas que el cuerpo técnico considera más relevantes para cada posición — tienen mayor peso en la puntuación final. Cuando varios scouts han observado al mismo jugador, el sistema calcula automáticamente una puntuación de consenso ponderada, ajustada además por el grado de familiaridad de cada scout con ese jugador (número de observaciones previas).

### Pipeline de captación
Cada jugador tiene un estado de captación: *Descartar*, *No por ahora*, *Seguir* o *Prioridad*. El responsable actualiza este estado en función de los informes agregados y las necesidades del equipo. La vista de pipeline muestra todos los objetivos activos organizados por estado, permitiendo gestionar el embudo de captación en tiempo real.

### Shortlists
Los scouts y el responsable pueden organizar jugadores en listas de trabajo con nombre propio — por ejemplo, por posición de necesidad o por área geográfica. Las shortlists sirven como colecciones de trabajo para las ventanas de fichajes.

### Comparación de jugadores
Comparación en paralelo de dos jugadores a lo largo de todas las dimensiones de métricas, útil cuando el club debe elegir entre perfiles similares para una misma posición.

### Exportación a PDF
Los informes individuales y los perfiles completos de jugadores pueden exportarse a PDF para presentaciones al cuerpo técnico o a la dirección deportiva.

### Copia de seguridad de datos
El responsable puede exportar la base de datos completa de jugadores e informes en formato CSV para archivo externo.

### Control de acceso por roles
El sistema cuenta con dos roles activos. Los scouts pueden crear y editar sus propios informes y registrar jugadores. El responsable de scouting tiene acceso completo, incluyendo la capacidad de cambiar el estado final de captación de un jugador y acceder a la configuración administrativa.

---

## Stack tecnológico

| Capa | Tecnología |
|---|---|
| Frontend | Next.js 16, React 19, TypeScript |
| Estilos | Tailwind CSS 4 |
| Base de datos local | Dexie (IndexedDB) |
| Backend y autenticación | Supabase (PostgreSQL + Row Level Security) |
| Generación de PDF | pdf-lib |
| Gráficos | Recharts |
| Despliegue | Vercel |
| PWA | next-pwa |

---

## Impacto en el proceso de scouting

- **Criterios estandarizados en todo el equipo de scouting.** Cada scout evalúa a los jugadores con las mismas métricas específicas por posición, definidas y consensuadas con el cuerpo técnico. La variabilidad entre scouts queda reducida a diferencias genuinas de observación, no a diferencias en los marcos de evaluación.

- **Historial de jugadores persistente.** Todo jugador observado alguna vez permanece en el sistema con un registro completo de informes. Un jugador que estaba en "no por ahora" hace seis meses puede revisarse con todo el contexto histórico.

- **Pipeline de captación cuantificado.** El responsable ve de un vistazo cuántos jugadores hay en cada estado para cada posición de necesidad, y puede trazar cualquier recomendación hasta los informes concretos que la sustentan.

- **Herramienta preparada para el campo.** La arquitectura offline-first permite a los scouts completar informes durante un partido sin preocuparse por la conectividad. Los informes se almacenan localmente y se sincronizan de forma automática cuando hay conexión disponible.

- **Ponderación alineada con el cuerpo técnico.** Al codificar las prioridades del cuerpo técnico directamente en los pesos de las métricas, el sistema garantiza que las puntuaciones automáticas reflejen lo que el equipo técnico realmente valora, no un modelo genérico de fútbol.

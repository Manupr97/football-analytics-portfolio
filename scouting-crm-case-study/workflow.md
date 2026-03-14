# Flujo de trabajo — CAC Scouting CRM

## Roles

El sistema cuenta con dos roles activos con responsabilidades diferenciadas:

| Rol | Responsabilidades |
|---|---|
| **Scout** | Asiste a partidos, registra jugadores, redacta informes |
| **Responsable** | Revisa los datos agregados, gestiona el pipeline de captación, toma las decisiones finales |

---

## 1. Registro de un jugador

Antes de poder redactar un informe, el jugador debe existir en el sistema. Si aún no está registrado, el scout crea un perfil con:

- Nombre completo
- Fecha de nacimiento y nacionalidad
- Posición habitual (mapeada a la taxonomía de posiciones del sistema)
- Club actual y nivel competitivo

Los nombres de equipos y competiciones se seleccionan desde un catálogo compartido mantenido por el responsable, garantizando una nomenclatura consistente entre todos los scouts.

Si el jugador ya está en el sistema — registrado por otro scout en un partido anterior — no se crea un duplicado. El scout va directamente a redactar un nuevo informe sobre el perfil existente.

---

## 2. Redacción de un informe de scouting

Esta es la acción central y cotidiana del sistema, diseñada para completarse **durante o inmediatamente después de un partido** desde un dispositivo móvil.

El scout navega al perfil del jugador y abre un nuevo informe. El formulario se adapta a la **posición observada** en ese partido concreto. Si un jugador actúa en un rol diferente al habitual, el scout selecciona la posición apropiada para esa observación.

### Evaluación de métricas

El formulario presenta entre 8 y 12 métricas organizadas en cuatro dimensiones:

- **Técnica** — control de balón, pase, finalización, etc. (específicas por posición)
- **Táctica** — posicionamiento, lectura del juego, inteligencia defensiva y ofensiva
- **Física** — velocidad, potencia, resistencia, juego aéreo
- **Mental** — toma de decisiones, competitividad, liderazgo

Cada métrica se puntúa del **1 al 10** usando anclas definidas:

| Puntuación | Significado |
|---|---|
| 1–3 | Muy por debajo del estándar de la categoría |
| 4–5 | Por debajo del estándar |
| 6–7 | Estándar competitivo de la categoría |
| 8–9 | Por encima del estándar — perfil diferencial |
| 10 | Excepcional — solo cuando ninguna acción en esa dimensión podría haber sido mejor |

Las anclas se describen en lenguaje llano para cada métrica, de modo que todos los scouts apliquen los mismos puntos de referencia independientemente de su interpretación individual.

### Contexto del scout

El sistema registra automáticamente cuántos informes previos ha redactado el scout sobre ese jugador. Este valor — **scout context** — se utiliza después en el cálculo del consenso ponderado. La tercera observación de un scout sobre el mismo jugador tiene más peso que la primera.

### Recomendación

Al final del formulario, el scout selecciona una de cuatro recomendaciones de captación:

| Recomendación | Criterio |
|---|---|
| **Descartar** | No alcanza el umbral mínimo del club |
| **No por ahora** | Tiene condiciones pero el momento no es el adecuado (contrato, edad, posición cubierta) |
| **Seguir** | Perfil interesante que necesita más observaciones antes de decidir |
| **Prioridad** | Listo para iniciar captación activa en la ventana actual o la próxima |

La recomendación no se deriva mecánicamente de la puntuación. Un jugador con una media de 7,5 puede ser *Prioridad* si cubre una necesidad posicional urgente; un jugador con un 8,0 puede estar en *Seguir* si la posición ya está cubierta.

### Campo de notas

Observaciones en texto libre: contexto sobre las condiciones del partido, acciones concretas destacadas, rasgos de carácter, historial de lesiones observado o cualquier matiz que las métricas estructuradas no puedan capturar.

---

## 3. Comportamiento sin conexión

El informe se guarda en local en el momento en que el scout pulsa "Guardar". No se requiere conexión a internet. La app pone el informe en cola y lo sincroniza con la nube la próxima vez que haya conectividad disponible — de forma automática, en segundo plano, sin ninguna acción requerida por parte del scout.

Si la sincronización falla (por ejemplo, si la conexión cae a mitad de la subida), el sistema reintenta automáticamente en los ciclos de sincronización siguientes. El scout ve un indicador de estado de sincronización pero nunca se le pide que reintente manualmente.

---

## 4. Revisión por el responsable y gestión del pipeline

El responsable accede al sistema desde un navegador (escritorio o móvil). Ve en tiempo real todos los datos de todos los scouts, según se van sincronizando.

### Dashboard

El dashboard ofrece una visión general del pipeline de captación: número de jugadores en cada estado, actividad reciente y alertas sobre jugadores que superan determinados umbrales.

### Perfil de jugador

Para cada jugador, el responsable ve:

- **Puntuación agregada por dimensión** — ponderada automáticamente por la prioridad de las métricas y el contexto del scout.
- **Informes individuales** — el informe completo de cada scout, visible por separado.
- **Recomendación de consenso** — el patrón de recomendaciones entre los distintos observadores.
- **Estado de captación** — la decisión actual del responsable sobre ese jugador.

### Consenso ponderado

Cuando varios scouts han observado al mismo jugador, el sistema calcula una puntuación de consenso automatizada. La ponderación tiene dos capas:

1. **Peso de la métrica** — las métricas prioritarias (marcadas por el cuerpo técnico) contribuyen 1,5× a la puntuación de la dimensión.
2. **Peso del contexto del scout** — el informe de un scout tiene más peso cuantas más veces haya observado previamente a ese jugador concreto: la primera observación lleva peso estándar; tres o más observaciones llevan un peso de 1,5×.

La puntuación de consenso resultante ofrece al responsable una visión cuantificada y multi-observador del jugador, preservando el acceso a cada informe individual para el contexto cualitativo.

### Cambio de estado de captación

Solo el responsable puede cambiar el estado final de captación de un jugador. Este es el punto de decisión clave: un jugador pasa de *Seguir* a *Prioridad* cuando el responsable determina que la evidencia agregada justifica activar la captación. El cambio queda registrado con un timestamp y es visible para todos los scouts.

---

## 5. Shortlists

Las shortlists son colecciones de trabajo que los scouts y el responsable utilizan para organizar jugadores con un propósito concreto — por ejemplo:

- "Laterales izquierdos — mercado de invierno"
- "Sub-23 en Tercera Federación Grupo 10"
- "Jugadores observados en la provincia de Córdoba"

Un jugador puede aparecer en varias shortlists. Las shortlists no afectan al estado de captación: son herramientas organizativas, no etapas del pipeline.

---

## 6. Comparación de jugadores

Cuando el responsable debe elegir entre dos candidatos para la misma posición, puede abrir una vista de comparación en paralelo. La vista muestra las puntuaciones agregadas de ambos jugadores en todas las métricas compartidas, facilitando la identificación de dónde divergen los perfiles.

---

## 7. Informes en PDF

En cualquier momento, el responsable o el scout pueden exportar:

- **Informe de scouting individual** — un PDF formateado de un informe concreto, apto para compartir con el cuerpo técnico.
- **Perfil completo del jugador** — un PDF resumen con puntuaciones agregadas, todos los informes e historial de captación.

Los PDFs se generan en el cliente sin necesidad de llamada al servidor.

---

## 8. Copia de seguridad de datos

El responsable puede descargar una exportación CSV completa de todos los jugadores e informes desde el panel de configuración. Sirve como archivo externo independiente de la base de datos en la nube. La exportación incluye todos los registros históricos, incluidos los jugadores que han sido borrados lógicamente de las vistas activas.

---

## Resumen del flujo de trabajo

```
Día de partido
    │
    ├── Scout abre la app en el móvil (funciona sin conexión)
    ├── Registra al jugador si no está en el sistema
    ├── Rellena el informe específico por posición durante / tras el partido
    ├── Guarda → almacenado en local de inmediato
    └── La app sincroniza con la nube cuando hay WiFi disponible

Entre partidos
    │
    ├── El responsable revisa los nuevos informes en el dashboard
    ├── Ve las puntuaciones de consenso agregadas por jugador
    ├── Ajusta el estado de captación conforme se acumula evidencia
    └── Gestiona shortlists para las próximas ventanas de fichajes

Decisión de fichaje
    │
    ├── El jugador alcanza el estado "Prioridad"
    ├── El responsable exporta el PDF para presentación al cuerpo técnico
    └── El proceso de fichaje comienza fuera del sistema
```

# Arquitectura — CAC Scouting CRM

## Visión general

El sistema sigue una arquitectura **offline-first con sincronización al reconectar**. El cliente es una Progressive Web App que mantiene una base de datos local completa en el dispositivo. Todas las acciones del usuario se escriben primero en local y se propagan a la nube en segundo plano. Este diseño se eligió específicamente por el contexto de trabajo sobre el terreno: los scouts operan en estadios y campos de entrenamiento donde el WiFi es irregular o inexistente.

---

## Capas de la arquitectura

```
┌─────────────────────────────────────────────────────┐
│                    CLIENTE (PWA)                     │
│                                                     │
│  ┌─────────────────┐    ┌─────────────────────────┐ │
│  │   Capa de UI    │    │   Motor de Sincronización│ │
│  │  (Next.js/React)│    │  push / pull / outbox   │ │
│  └────────┬────────┘    └───────────┬─────────────┘ │
│           │                         │               │
│  ┌────────▼─────────────────────────▼─────────────┐ │
│  │          Base de datos local (IndexedDB/Dexie) │ │
│  └─────────────────────────────────────────────────┘ │
└─────────────────────────┬───────────────────────────┘
                          │ HTTPS (cuando hay conexión)
┌─────────────────────────▼───────────────────────────┐
│                   SUPABASE                          │
│                                                     │
│  ┌─────────────────┐    ┌─────────────────────────┐ │
│  │   PostgreSQL    │    │   Auth (JWT + RLS)      │ │
│  └─────────────────┘    └─────────────────────────┘ │
└─────────────────────────────────────────────────────┘
```

---

## Componentes

### 1. Progressive Web App (PWA)

Construida con Next.js y desplegada en Vercel. Instalable en dispositivos móviles a través de la opción "Añadir a la pantalla de inicio" del navegador. El service worker generado por `next-pwa` permite que la app cargue y funcione sin conexión a internet tras la primera visita.

**Estructura de rutas:**

- `/login` — Pública. Autenticación por email y contraseña a través de Supabase Auth.
- `/dashboard` — Protegida. Vista general del pipeline de captación.
- `/players` — Registro de jugadores. Listado, búsqueda y filtrado por estado y posición.
- `/players/[id]` — Perfil individual de jugador con puntuaciones agregadas e historial de informes.
- `/players/[id]/reports/new` — Formulario de informe de scouting (métricas específicas por posición).
- `/players/compare` — Comparación de dos jugadores en paralelo.
- `/shortlists` — Colecciones de jugadores con nombre.
- `/settings` — Gestión de catálogos de competiciones y equipos; copia de seguridad en CSV (solo responsable).

### 2. Base de datos local (IndexedDB mediante Dexie)

Cada dispositivo que ejecuta la app mantiene una copia local completa de los datos a los que tiene acceso. Esto incluye jugadores, informes, shortlists, perfiles de usuario y catálogos de competiciones y equipos. Todas las escrituras ocurren primero en local.

La base de datos local está versionada. Cuando el esquema de datos cambia (nuevos índices), la versión de la base de datos se incrementa para forzar una migración en el navegador sin pérdida de datos.

Una tabla dedicada de **outbox** almacena las operaciones de sincronización fallidas con lógica de reintento (hasta 3 intentos). Esto garantiza que las operaciones intentadas sin conectividad se reintenten automáticamente al reconectar, en lugar de perderse silenciosamente.

### 3. Motor de sincronización

Un proceso en segundo plano se ejecuta cada 10 segundos mientras la app está activa. Ejecuta tres pasos en orden:

1. **Procesamiento del outbox** — Reintenta las operaciones que fallaron previamente.
2. **Push** — Envía a Supabase todos los registros creados o modificados en local que aún no han llegado al servidor.
3. **Pull** — Descarga los cambios remotos y los fusiona con la base de datos local.

La resolución de conflictos usa una estrategia de **last-write-wins** basada en el timestamp `updatedAt`. La secuencia del pull respeta las dependencias: los perfiles de usuario se descargan antes que los informes, ya que los informes referencian nombres de scouts que se resuelven desde la tabla de perfiles.

### 4. Backend Supabase

Supabase proporciona tres servicios:

- **PostgreSQL** — La fuente de verdad para todos los datos. El esquema se gestiona mediante archivos de migración SQL versionados.
- **Autenticación** — Login por email y contraseña con tokens JWT. Las sesiones las gestiona la librería cliente de Supabase.
- **Row Level Security (RLS)** — Todas las tablas tienen políticas RLS activas. Los scouts solo pueden leer y escribir sus propios registros; el responsable tiene acceso más amplio. Esto se aplica a nivel de base de datos, no solo en el código de la aplicación.

---

## Modelo de datos (conceptual)

```
Jugador
  ├── id, nombre, posición, fecha_nacimiento, nacionalidad
  ├── equipo_actual (→ Equipo)
  ├── estado_captación: descartar | no_por_ahora | seguir | prioridad
  ├── deletedAt (borrado lógico)
  └── Informes[]
        ├── scout_id (→ PerfilUsuario)
        ├── competición (→ Competición)
        ├── posición_observada
        ├── métricas (JSON — dimensiones puntuadas por posición)
        ├── puntuación_global
        ├── recomendación
        ├── scout_context (número de observaciones previas)
        └── notas

PerfilUsuario
  └── rol: scout | responsable | dd

Shortlist
  └── ShortlistItems[] (→ Jugadores)

Competición / Equipo (catálogos editables por el responsable)
```

---

## Resumen del stack

| Necesidad | Solución | Justificación |
|---|---|---|
| Capacidad offline | IndexedDB (Dexie) | Los scouts trabajan en zonas sin WiFi |
| Fiabilidad de sync | Patrón outbox + cola de reintentos | Garantiza que ningún informe se pierde silenciosamente |
| Backend | Supabase (PostgreSQL) | Gestionado, escalable, auth y RLS integrados |
| Auth y permisos | Supabase Auth + RLS | Seguridad aplicada en la BD, no solo en la UI |
| Frontend | Next.js + TypeScript | Tipado estático, compatible con PWA, despliegue en Vercel |
| Generación de PDF | pdf-lib | En el cliente, sin necesidad de llamada al servidor |
| Despliegue | Vercel | Configuración cero para Next.js, CDN global |

---

## Flujo de datos

```
Scout rellena informe en el móvil (sin WiFi)
        │
        ▼
Se escribe en IndexedDB (local) de inmediato
        │
        ▼
La UI confirma el guardado al instante
        │
        ▼
[se recupera la conexión]
        │
        ▼
Motor de sync se activa (intervalo de 10s)
        │
        ├── Push: registro local → Supabase
        └── Pull: cambios remotos → fusión en local
                │
                ▼
        El dashboard del responsable refleja el nuevo informe
```

---

## Modelo de seguridad

- Todas las llamadas a la API se autentican mediante tokens JWT emitidos por Supabase Auth.
- Las políticas de Row Level Security garantizan que, aunque un cliente envíe una petición malformada, la base de datos rechazará lecturas y escrituras no autorizadas.
- Los roles de los scouts se almacenan en una tabla `profiles` gestionada en el servidor. Las verificaciones de rol en la UI se complementan con las políticas RLS en el servidor: las comprobaciones de rol en la UI son solo para la experiencia de usuario, no para la seguridad.
- La app utiliza la clave anon de Supabase, que no tiene privilegios elevados. Todo el acceso a datos pasa por RLS.

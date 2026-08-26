# Transmití tu foto

Los invitados de un evento escanean un QR, mandan una foto desde el celular y
—después de que un moderador la aprueba— la foto aparece proyectada en la
pantalla del salón. Varios eventos a la vez, aislados entre sí.

La especificación completa está en [CONSTRUIR-APP.md](CONSTRUIR-APP.md). Las
reglas permanentes para trabajar en el repo están en [CLAUDE.md](CLAUDE.md).

**Estado: Fases 0, 1 y 2 terminadas.** El backend responde los 14 endpoints del
contrato, con base de datos, modelos y autenticación reales. Los endpoints de
fotos, moderación y descarga todavía devuelven datos fijos: llegan en las
Fases 3 y 4. Del frontend todavía no hay nada (Fases 5 a 8).

---

## Qué necesitás instalado

| Herramienta | Versión | Para qué |
|---|---|---|
| Docker Desktop | cualquiera reciente | Postgres local |
| Python | 3.12 | el backend |
| Node.js | 20 o más | el frontend |

## Puesta en marcha

```bash
cp .env.example .env
```

Editá `.env`. Para desarrollo local, comentá la línea de Supabase y descomentá
la de docker compose que está justo abajo.

```bash
docker compose up -d
```

La primera vez que levanta, Postgres aplica solo `db/schema.sql` y después
`db/seed.sql`. Queda escuchando en `localhost:5432` con usuario, contraseña y
base `transmiti`.

Para volver a aplicar los SQL desde cero hay que borrar el volumen:

```bash
docker compose down -v && docker compose up -d
```

### Backend (desde la Fase 1)

```bash
cd backend && python -m venv .venv && .venv/Scripts/activate && pip install -r requirements.txt
```

```bash
cd backend && uvicorn app.main:app --reload
```

### Frontend (desde la Fase 5)

```bash
cd frontend && npm install
```

```bash
cd frontend && npm run dev
```

---

## Comandos

    docker compose up -d                       # Postgres local
    docker compose down -v                     # apagar y borrar los datos
    docker compose exec db psql -U transmiti   # consola SQL
    cd backend && uvicorn app.main:app --reload   # API en :8000, /docs para probarla
    cd backend && alembic upgrade head           # migraciones
    cd backend && pytest                         # pruebas
    cd frontend && npm run dev                   # SPA en :5173

### Pruebas

`pytest` corre siempre. Las pruebas que necesitan Postgres se saltean solas si
no encuentra la variable `DATABASE_URL_TEST`, así que en una máquina sin base
igual se verifica el contrato completo. Para correrlas todas, apuntá a una base
**vacía y descartable** — el fixture borra y recrea el esquema en cada corrida:

    DATABASE_URL_TEST=postgresql+psycopg://transmiti:transmiti@localhost:5432/transmiti_test pytest

---

## Datos de desarrollo

El seed deja cargados los casos que rompen las pantallas: fotos verticales,
horizontales, cuadradas y panorámicas; nombres con acentos y ñ, uno vacío y
tres sin nombre; y fotos repartidas a lo largo de dos horas.

**Administrador:** `ana@transmitifoto.test` / `fiesta1234`

| Evento | Estado | Código público | Token de pantalla |
|---|---|---|---|
| Casamiento Ana y Juan | activo | `ab12cd34` | `64syPN4YFgbJibLfIOlrjI51R0HFlKDm` |
| Cumple de 15 de Malena | cerrado | `ef56gh78` | `8MX4OqECds7IhkCmlK7vub76PntouGz1` |

Fotos del evento activo: 20 (12 aprobadas, 5 pendientes, 3 rechazadas).
Fotos del evento cerrado: 4 (3 aprobadas, 1 pendiente).

El dispositivo `9f2c1a7b…` ya subió 8 de sus 10 fotos: alcanza con mandar dos
más para probar el `LIMITE_ALCANZADO` sin tocar la base.

Las cuatro fotos del evento cerrado tienen el cartel **EVENTO-B** quemado en la
imagen. Si alguna aparece en la pantalla del evento activo, hay una fuga entre
eventos y se ve sin mirar la base.

Rutas útiles una vez que exista el frontend:

    /e/ab12cd34                                   # invitado, evento activo
    /e/ef56gh78                                   # invitado, evento cerrado
    /p/64syPN4YFgbJibLfIOlrjI51R0HFlKDm           # pantalla, evento activo
    /p/8MX4OqECds7IhkCmlK7vub76PntouGz1           # pantalla, evento cerrado
    /admin/login                                  # panel

### Sobre las imágenes del seed

Las URLs apuntan a la nube pública `demo` de Cloudinary y funcionan de verdad,
así que se puede maquetar contra fotos reales sin tener una cuenta propia. Los
`bytes` de cada fila son el tamaño medido de esa URL.

El `public_id`, en cambio, sigue la convención del sistema
(`eventos/{codigo_publico}/…`) y por eso no se corresponde con el public_id real
dentro de la nube `demo`. Es a propósito: así el seed cumple la regla 4 de
CLAUDE.md y la verificación de carpeta se puede probar. La consecuencia para la
Fase 4 es que el ZIP tiene que armarse descargando `url`, no resolviendo
`public_id` contra la cuenta propia de Cloudinary.

---

## Estructura

    db/          esquema y datos de desarrollo
    backend/     API FastAPI          (Fases 1 a 4)
    frontend/    SPA React            (Fases 5 a 8)

## Trampas conocidas

Están todas en [CLAUDE.md](CLAUDE.md), pero las dos que más tiempo hacen perder:

- **Supabase:** usar la cadena del pooler en modo sesión. La conexión directa
  resuelve por IPv6 y falla desde Render con un error que parece de credenciales.
- **Render gratuito:** el servicio se duerme. Abrir la pantalla diez minutos
  antes del evento.

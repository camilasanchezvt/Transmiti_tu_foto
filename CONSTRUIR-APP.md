# Transmití tu foto — Brief de construcción para Claude Code

Documento único para construir la aplicación completa. Está escrito para que un agente de código lo siga sin tener que preguntar nada.

**Cómo se usa:** creá una carpeta vacía, guardá este archivo adentro como `CONSTRUIR-APP.md`, abrí Claude Code ahí y pegá el prompt de arranque de la sección 12. Después, una fase por sesión.

---

## 1. Qué es la aplicación

Sistema para que los invitados de un evento manden fotos desde el celular escaneando un QR, y que esas fotos —después de que un administrador las aprueba— se proyecten automáticamente en una pantalla del salón.

Tres interfaces, un backend, varios eventos simultáneos sin que se mezclen entre sí.

| Interfaz | Ruta | Quién la usa | Contexto de uso |
|---|---|---|---|
| App del invitado | `/e/:codigo` | Invitados | Celular, salón oscuro, datos móviles, una mano |
| Pantalla de proyección | `/p/:token` | Nadie: corre sola | Notebook conectada a un proyector, tres horas |
| Panel de administración | `/admin/*` | Un moderador | Notebook, durante el evento, con apuro |

### El recorrido completo

1. El administrador crea el evento y obtiene un **código público** (para el QR) y un **token de pantalla** (para la proyección).
2. El invitado escanea el QR y abre `/e/:codigo`.
3. Elige una foto. El navegador **la comprime antes de subir**.
4. El navegador le pide una **firma** al backend y sube la foto **directo a Cloudinary**. Los bytes nunca pasan por el servidor.
5. El navegador le avisa al backend, que guarda el registro con estado `pendiente`.
6. El moderador la aprueba desde el panel.
7. La pantalla, que consulta cada pocos segundos pidiendo sólo lo nuevo, la muestra en menos de veinte segundos.
8. Al terminar el evento, el administrador lo cierra y descarga todas las fotos en un ZIP.

---

## 2. Stack

| Capa | Tecnología | Notas |
|---|---|---|
| Backend | Python 3.12 · FastAPI · SQLAlchemy 2.0 · Alembic | Pydantic v2 para los esquemas |
| Base de datos | PostgreSQL 16, alojado en **Supabase** | Sólo como base de datos |
| Imágenes | **Cloudinary**, subida firmada desde el navegador | El backend sólo firma |
| Frontend | React 18 · Vite · TypeScript · Tailwind CSS · React Router | Una sola SPA con tres zonas |
| Despliegue | **Render**: un web service para la API, un static site para el frontend | |
| Autenticación | JWT propio (`pyjwt`) + `passlib[bcrypt]` | Sólo para el administrador |

### Reglas de stack que no se negocian

- **Supabase se usa únicamente como PostgreSQL.** Nada de `supabase-js`, PostgREST, Supabase Auth ni Supabase Storage. Si una pantalla consulta Supabase directamente, se saltea el backend y con él las reglas de moderación y el aislamiento entre eventos.
- **La conexión a Supabase desde Render usa la cadena del pooler en modo sesión.** La conexión directa resuelve por IPv6 y falla desde Render con un error de red que parece de credenciales.
- **El `CLOUDINARY_API_SECRET` nunca sale del backend.** No se importa, no se referencia, no aparece en ninguna variable `VITE_*`.
- **No se agregan librerías fuera de las listadas** sin que esté justificado en el prompt de la fase.

---

## 3. Estructura del repositorio

```
transmiti-tu-foto/
├── CLAUDE.md                    # reglas permanentes (sección 11)
├── CONSTRUIR-APP.md             # este archivo
├── README.md                    # instalación y comandos
├── docker-compose.yml           # Postgres local
├── .env.example
├── .gitignore
├── db/
│   ├── schema.sql
│   └── seed.sql
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py              # app FastAPI, CORS, routers, manejador de errores
│   │   ├── config.py            # settings desde entorno (pydantic-settings)
│   │   ├── database.py          # engine, SessionLocal, get_db
│   │   ├── models.py            # Administrador, Evento, Foto
│   │   ├── schemas.py           # modelos Pydantic de entrada y salida
│   │   ├── security.py          # hash de contraseñas, crear y validar JWT
│   │   ├── deps.py              # admin_actual, evento_por_codigo, evento_por_token
│   │   ├── errores.py           # ErrorApp y códigos
│   │   ├── ratelimit.py         # límite en memoria por IP y evento
│   │   ├── cloudinary_service.py# firma y armado del ZIP
│   │   └── routers/
│   │       ├── publico.py       # /api/e/*
│   │       ├── pantalla.py      # /api/pantalla/*
│   │       └── admin.py         # /api/admin/*
│   ├── alembic/
│   ├── tests/
│   ├── requirements.txt
│   └── alembic.ini
└── frontend/
    ├── index.html
    ├── package.json
    ├── vite.config.ts
    ├── tailwind.config.js
    ├── tsconfig.json
    └── src/
        ├── main.tsx
        ├── App.tsx              # rutas
        ├── api/
        │   ├── client.ts        # fetch con manejo de errores
        │   └── tipos.ts         # tipos compartidos con el backend
        ├── comp/                # componentes compartidos por las tres zonas
        │   ├── Boton.tsx
        │   ├── Cargando.tsx
        │   ├── MensajeError.tsx
        │   └── Foto.tsx
        ├── lib/
        │   ├── comprimir.ts     # redimensionado y recompresión
        │   ├── subir.ts         # XHR a Cloudinary con progreso
        │   └── dispositivo.ts   # hash persistente del dispositivo
        ├── invitado/
        │   ├── PaginaInvitado.tsx
        │   └── textos.ts
        ├── pantalla/
        │   ├── PaginaPantalla.tsx
        │   ├── useCola.ts       # buffer, polling incremental, precarga
        │   └── QR.tsx
        └── admin/
            ├── PaginaLogin.tsx
            ├── PaginaEventos.tsx
            ├── PaginaModerar.tsx
            ├── PaginaCierre.tsx
            └── useAtajos.ts
```

---

## 4. Modelo de datos

Tres tablas. El archivo `db/schema.sql` se crea exactamente así.

```sql
CREATE TABLE administradores (
  id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  email         text NOT NULL UNIQUE,
  nombre        text NOT NULL,
  password_hash text NOT NULL,
  creado_en     timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE eventos (
  id             bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  admin_id       bigint NOT NULL REFERENCES administradores(id),
  nombre         text NOT NULL,
  fecha_evento   date NOT NULL,
  codigo_publico text NOT NULL UNIQUE,
  token_pantalla text NOT NULL UNIQUE,
  estado         text NOT NULL DEFAULT 'borrador'
                 CHECK (estado IN ('borrador','activo','cerrado')),
  max_fotos_por_dispositivo int NOT NULL DEFAULT 10,
  segundos_por_foto         int NOT NULL DEFAULT 7,
  creado_en      timestamptz NOT NULL DEFAULT now(),
  cerrado_en     timestamptz
);

CREATE TABLE fotos (
  id               bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  evento_id        bigint NOT NULL REFERENCES eventos(id) ON DELETE CASCADE,
  public_id        text NOT NULL UNIQUE,
  url              text NOT NULL,
  ancho            int,
  alto             int,
  bytes            int,
  estado           text NOT NULL DEFAULT 'pendiente'
                   CHECK (estado IN ('pendiente','aprobada','rechazada')),
  dispositivo_hash text,
  nombre_invitado  text,
  subida_en        timestamptz NOT NULL DEFAULT now(),
  moderada_en      timestamptz,
  moderada_por     bigint REFERENCES administradores(id)
);

-- El índice del polling de la pantalla. Sin este, a las 200 fotos se arrastra.
CREATE INDEX idx_fotos_pantalla ON fotos (evento_id, estado, id);

-- Índice parcial: sólo las pendientes. Es el que usa la bandeja de moderación.
CREATE INDEX idx_fotos_pendientes ON fotos (evento_id, id) WHERE estado = 'pendiente';

-- Para el listado del panel, ordenado por lo más reciente.
CREATE INDEX idx_fotos_recientes ON fotos (evento_id, subida_en DESC);

-- Para contar cuántas subió un dispositivo.
CREATE INDEX idx_fotos_dispositivo ON fotos (evento_id, dispositivo_hash);
```

### Por qué tres identificadores por evento

| Campo | Largo | Quién lo tiene | Qué habilita |
|---|---|---|---|
| `id` | — | Sólo el servidor | Nada hacia afuera. **Nunca aparece en una respuesta pública.** |
| `codigo_publico` | 8 caracteres | Cualquiera que escanee el QR | Sólo subir fotos |
| `token_pantalla` | 32 caracteres | La notebook del proyector | Sólo leer las aprobadas |

Los dos se generan con `secrets.token_urlsafe`, nunca a partir del id ni de la fecha. Si fueran adivinables, el aislamiento entre eventos simultáneos no existiría.

### Convenciones

- Todas las marcas de tiempo son `timestamptz`. Nunca `timestamp` pelado: el servidor está en UTC y el evento en Argentina.
- Los estados son `text` con `CHECK`, no tipos ENUM.
- Nada se borra: una foto rechazada sigue existiendo y se puede revertir.

---

## 5. Contrato de API

Base: `/api`. Todo JSON. Todos los errores tienen la misma forma:

```json
{ "error": { "codigo": "EVENTO_CERRADO", "mensaje": "Este evento ya terminó" } }
```

### Códigos de error

`EVENTO_NO_ENCONTRADO` · `EVENTO_CERRADO` · `EVENTO_BORRADOR` · `FOTO_NO_ENCONTRADA` · `ARCHIVO_INVALIDO` · `PUBLIC_ID_AJENO` · `LIMITE_ALCANZADO` · `DEMASIADOS_PEDIDOS` · `NO_AUTORIZADO` · `DATOS_INVALIDOS`

### Públicos — los usa el celular del invitado

**`GET /api/e/{codigo_publico}`**
```json
200 → { "nombre": "Casamiento Ana y Juan", "fecha_evento": "2026-09-12",
        "estado": "activo", "max_fotos_por_dispositivo": 10 }
404 → EVENTO_NO_ENCONTRADO
```
Devuelve `estado` también cuando es `cerrado`, para que la app muestre la pantalla de cierre. Si es `borrador`, responde 404: un evento sin publicar no existe hacia afuera.

**`POST /api/e/{codigo_publico}/firma`**
```json
body → { "dispositivo_hash": "9f2c1a..." }
200  → { "cloud_name": "...", "api_key": "...", "timestamp": 1756200000,
         "signature": "...", "folder": "eventos/ab12cd34" }
409  → EVENTO_CERRADO · 429 → LIMITE_ALCANZADO | DEMASIADOS_PEDIDOS
```
Firma sólo `folder` y `timestamp`. La carpeta es siempre `eventos/{codigo_publico}`.

**`POST /api/e/{codigo_publico}/fotos`**
```json
body → { "public_id": "eventos/ab12cd34/k3j2h1", "url": "https://res.cloudinary.com/...",
         "ancho": 1600, "alto": 1200, "bytes": 348211,
         "dispositivo_hash": "9f2c1a...", "nombre_invitado": "Sofi" }
201  → { "id": 128, "estado": "pendiente" }
400  → ARCHIVO_INVALIDO · 403 → PUBLIC_ID_AJENO · 409 → EVENTO_CERRADO · 429 → LIMITE_ALCANZADO
```
**Verificación obligatoria:** el `public_id` recibido tiene que empezar con `eventos/{codigo_publico}/`. Sin esta línea, cualquiera puede registrar la URL de una imagen ajena y aparece proyectada.

### Pantalla — la usa la notebook del proyector

**`GET /api/pantalla/{token_pantalla}`**
```json
200 → { "evento": { "nombre": "...", "codigo_publico": "ab12cd34", "estado": "activo" },
        "config": { "segundos_por_foto": 7, "intervalo_polling_ms": 6000, "maximo_buffer": 200 } }
```

**`GET /api/pantalla/{token_pantalla}/fotos?desde=0&limite=40`**
```json
200 → { "fotos": [ { "id": 128, "url": "...", "ancho": 1600, "alto": 1200,
                     "nombre_invitado": "Sofi" } ], "ultimo_id": 128 }
```
Devuelve **sólo fotos aprobadas**. Dos comportamientos:
- `desde=0` → las últimas `limite` aprobadas, ordenadas de la más vieja a la más nueva. Es el arranque en frío.
- `desde=N` → las aprobadas con `id > N`, ascendente. Es el polling normal.

`ultimo_id` es el mayor id devuelto, o el `desde` recibido si no vino nada.

### Administración — requieren `Authorization: Bearer <token>`

| Método y ruta | Body | Respuesta |
|---|---|---|
| `POST /api/admin/login` | `{email, password}` | `{token, expira_en}` |
| `GET /api/admin/eventos` | — | lista con `{id, nombre, fecha_evento, estado, codigo_publico, token_pantalla, segundos_por_foto, max_fotos_por_dispositivo, pendientes, aprobadas, rechazadas}` |
| `POST /api/admin/eventos` | `{nombre, fecha_evento}` | el evento creado, con sus dos claves |
| `PATCH /api/admin/eventos/{id}` | `{estado?, segundos_por_foto?, max_fotos_por_dispositivo?}`, al menos uno. Segundos entre 3 y 30; fotos por invitado entre 1 y 50 | el evento actualizado |
| `GET /api/admin/eventos/{id}/fotos` | query: `estado`, `desde`, `limite` | `{fotos: [...], ultimo_id}` |
| `GET /api/admin/eventos/{id}/resumen` | — | `{pendientes, aprobadas, rechazadas}` |
| `PATCH /api/admin/fotos/{id}` | `{estado}` | `{id, estado}` |
| `POST /api/admin/fotos/lote` | `{ids: [], estado}` | `{afectadas: 12}` |
| `GET /api/admin/eventos/{id}/descarga` | query: `incluir=aprobadas\|todas` | archivo ZIP |
| `GET /api/salud` | — sin auth — | `{estado, base}` |

**Reglas de negocio**

- Un evento `cerrado` rechaza subidas nuevas pero **sigue sirviendo la pantalla**, para que las aprobadas terminen de pasar.
- Un evento `borrador` no acepta nada: ni subidas ni pantalla.
- Moderar es **idempotente**: aprobar dos veces la misma foto no rompe nada ni duplica registros.
- El límite por dispositivo se cuenta contra `dispositivo_hash`, sin pedirle datos al invitado.
- Sólo imágenes: `image/jpeg`, `image/png`, `image/webp`, `image/heic`. Nada de video.
- Una foto pertenece a un solo evento y no se puede mover.
- El endpoint de firma tiene límite de pedidos: 30 cada 10 minutos por IP y evento.

---

## 6. Especificación de la app del invitado

Ruta `/e/:codigo`. Cuatro estados en una sola pantalla, sin scroll.

1. **Bienvenida** — nombre del evento y un botón grande: *Elegir foto*. Sin login, sin registro.
2. **Elegir** — se abre la cámara o la galería del sistema operativo con un `<input type="file" accept="image/*">`. No construir un selector propio.
3. **Subiendo** — vista previa y **barra de progreso real** (evento `progress` del XHR), nunca un girador falso.
4. **Listo** — confirmación que explica la espera, y un botón para mandar otra.

### La compresión: es lo que decide si funciona el día del evento

Una foto de celular pesa entre 4 y 6 MB. Ochenta invitados colgados de la misma antena de datos no pueden subir eso. La compresión ocurre **en el navegador, antes de subir**:

```
1. createImageBitmap(file, { imageOrientation: 'from-image' })
   ← esto resuelve la rotación EXIF de las fotos de iPhone,
     que si no aparecen acostadas en el proyector
2. calcular escala para que el lado mayor quede en 1600 px (nunca agrandar)
3. dibujar en un <canvas> de ese tamaño
4. canvas.toBlob(..., 'image/jpeg', 0.82)
5. si el blob resultante pesa más que el original, usar el original
```

Resultado esperado: de 4032×3024 y 4,8 MB a 1600×1200 y unos 340 KB. De unos 38 segundos de subida por datos móviles a unos 3.

Pasar la foto por este proceso también convierte los HEIC de iPhone a JPEG, que es lo que los navegadores muestran sin problemas.

### Subida a Cloudinary

`POST https://api.cloudinary.com/v1_1/{cloud_name}/image/upload` con `FormData`: `file`, `api_key`, `timestamp`, `signature`, `folder`. Los parámetros firmados tienen que coincidir exactamente con los enviados. Se usa `XMLHttpRequest` (no `fetch`) para poder leer el progreso de subida.

### Textos de la interfaz

Español rioplatense, en segunda persona, cortos. Van en `invitado/textos.ts`, no incrustados en el JSX.

| Momento | Texto |
|---|---|
| Bienvenida | Mandá tu foto y aparece en la pantalla |
| Botón principal | Elegir foto |
| Subiendo | Subiendo… 60% |
| Listo | ¡Llegó! En un rato la vas a ver en la pantalla |
| Otra más | Mandar otra |
| Error de red | No pudimos subirla. Probá de nuevo |
| Archivo inválido | Sólo podemos recibir fotos |
| Límite alcanzado | Ya mandaste tus 10 fotos. ¡Gracias! |
| Evento cerrado | Este evento ya terminó |

Ningún texto de la interfaz menciona palabras del sistema: ni "endpoint", ni "moderación", ni "servidor".

### Diseño

Botones de 56 px de alto como mínimo, contraste alto, texto grande, todo sin scroll. El usuario está en un salón oscuro, con una copa en la otra mano, y el brillo del celular bajo.

### Casos borde

| Situación | Comportamiento |
|---|---|
| Se corta la señal a mitad de subida | Reintenta una vez sola; después muestra error con botón de reintentar, **sin perder la foto elegida** |
| Doble toque en subir | El botón se deshabilita al primer toque |
| Sin permiso de cámara | Se ofrece la galería, sin cartel de error |
| Elige un video | Se rechaza antes de subir nada |
| Foto de 20 MB | Se comprime igual; el límite se aplica **después** de comprimir |
| Cierra la pestaña mientras sube | La foto llegó o no llegó, nunca queda a medias registrada |

---

## 7. Especificación de la pantalla de proyección

Ruta `/p/:token`. Corre sola durante horas delante de cien personas.

### Los cinco estados

| Estado | Cuándo | Qué se ve |
|---|---|---|
| Esperando | No hay aprobadas todavía | QR **enorme** en el centro y una frase corta |
| Pasando fotos | Hay aprobadas | Foto a pantalla completa, QR chico en una esquina fija |
| Llegó una nueva | Entró una aprobada | Marca discreta y breve; **nunca cortando la transición en curso** |
| Sin conexión | El servidor no responde | Sigue pasando lo que tiene en memoria; indicador mínimo |
| Evento cerrado | `estado === 'cerrado'` | Desaparece el QR, queda un mensaje; las aprobadas siguen pasando |

### La cola — el corazón del asunto

```
Al montar:
  GET /api/pantalla/{token}/fotos?desde=0&limite=40  → buffer inicial
  guardar ultimo_id

Cada intervalo_polling_ms:
  GET .../fotos?desde={ultimo_id}
  las nuevas se insertan en buffer[indiceActual + 1]
    ← entran DETRÁS de la que está en pantalla, no al final:
      así el invitado que la mandó la ve antes de irse de la mesa
  actualizar ultimo_id

Antes de avanzar a la siguiente:
  precargar buffer[siguiente] con new Image() y esperar su onload
    ← sin esto hay un parpadeo gris en cada cambio,
      que en un proyector se nota muchísimo

Al llegar al final del buffer:
  volver al índice 0, con un reordenamiento leve
    ← un evento de tres horas con 50 fotos las repite muchas veces

Si buffer.length > maximo_buffer:
  descartar las más viejas, nunca las recién insertadas

Si una imagen falla al cargar (onerror):
  sacarla del buffer y avanzar; un 404 puntual no puede frenar el slideshow

Si el polling falla:
  reintentar con espera creciente: 5s, 10s, 20s, 40s, tope 60s
  seguir mostrando el buffer mientras tanto
```

### Presentación

- **Nunca deformar una foto.** Entra completa y centrada (`object-fit: contain`); el espacio que sobra se llena con la misma imagen ampliada y desenfocada de fondo.
- Transición: fundido de unos 700 ms. Tiempo por foto: el `segundos_por_foto` que manda el servidor.
- Fondo oscuro y texto blanco grande: un proyector en un salón con luz baja pierde mucho brillo.
- **Tamaño del QR:** un QR se escanea cómodo hasta unas diez veces su propio lado. Con la persona más lejana a ocho metros, el QR proyectado tiene que medir cerca de ochenta centímetros — más de un cuarto del ancho de una proyección de tres metros. Mucho más grande de lo que parece necesario en la notebook.
- Pantalla completa real (Fullscreen API), sin scroll, cursor oculto, `navigator.wakeLock` para que la máquina no se suspenda.
- Si alguien sale de pantalla completa con Escape, que se vuelva a entrar con una tecla o un click en cualquier lado.

---

## 8. Especificación del panel de administración

Rutas `/admin/login`, `/admin`, `/admin/eventos/:id/moderar`, `/admin/eventos/:id/cierre`.

### Alta de evento

Nombre y fecha, nada más. Al crearlo, la pantalla muestra lo que se necesita de verdad: el **QR descargable en PNG** para imprimir y poner en las mesas, y el **link de la pantalla** para abrir en la notebook del proyector, ambos con botón de copiar.

### La bandeja de moderación

Es la pantalla que importa: se usa tres horas seguidas, con gente esperando. **Objetivo medible: cincuenta fotos en menos de dos minutos.** De ahí salen seis decisiones.

1. **Teclado antes que mouse.** `←` `→` navegar, `A` aprobar, `R` rechazar, `Z` deshacer. Con mouse son cincuenta apuntadas y cincuenta clics; con teclado son cincuenta pulsaciones sin mover la mano.
2. **Foto grande y fila de miniaturas.** Se decide mirando la foto en grande, no la miniatura.
3. **Respuesta inmediata, confirmación después.** Al apretar `A` la foto sale de la lista al instante y se pasa a la siguiente; el pedido viaja en segundo plano. Si falla, la foto vuelve con un aviso. Esperar la respuesta entre foto y foto convierte dos minutos en diez.
4. **Aprobación en lote.** Selección múltiple con `Shift` y aprobar todo con un solo pedido a `/api/admin/fotos/lote`. En una fiesta llegan ráfagas de veinte fotos casi todas buenas.
5. **Auto-refresco que no mueve la posición.** Cada 10 s se buscan las nuevas, pero no se reordena lo que se está mirando: aparece un aviso discreto — *12 nuevas* — y se incorporan al terminar la tanda. Una lista que se reacomoda sola hace que se apruebe la foto equivocada.
6. **Contador de pendientes siempre visible**, arriba y grande. Es la única métrica que importa en vivo.

**Sin confirmaciones.** Nada de "¿estás segura?" antes de rechazar: duplica los clics de la tarea que más se repite para prevenir un error que se deshace con una tecla. La red de seguridad es `Z`, no un cartel.

### Aislamiento del lado de la persona

El backend garantiza que las fotos no se mezclen. Lo que ninguna base de datos previene es que el moderador apruebe fotos del evento equivocado con dos pestañas abiertas. Tres cosas lo resuelven: una **barra de contexto fija** con el nombre del evento, un **color asignado por evento** para distinguir pestañas de un vistazo, y el **nombre del evento en el título de la pestaña**.

### Cierre y descarga

Cerrar el evento deja de aceptar fotos y muestra el mensaje de cierre en la pantalla, pero las aprobadas siguen pasando. La descarga permite elegir todas o sólo las aprobadas, muestra progreso (doscientas fotos no salen en dos segundos) y nombra el archivo con el evento y la fecha, no con un identificador.

**Ojo con la memoria de Render:** el ZIP se arma en streaming, no juntando todo en memoria, o con doscientas fotos el servicio se cae.

---

## 9. Variables de entorno

`.env.example` en la raíz. Los nombres van al repositorio, los valores nunca.

```bash
# ── Backend ────────────────────────────────────────────────
# La cadena del POOLER EN MODO SESIÓN de Supabase.
# La conexión directa resuelve por IPv6 y falla desde Render.
DATABASE_URL=postgresql+psycopg://usuario:clave@aws-0-region.pooler.supabase.com:5432/postgres

CLOUDINARY_CLOUD_NAME=xxxxx
CLOUDINARY_API_KEY=xxxxx
CLOUDINARY_API_SECRET=xxxxx        # NUNCA llega al navegador

JWT_SECRET=cadena-larga-al-azar
JWT_HORAS=12
CORS_ORIGINS=http://localhost:5173,https://transmitifoto.onrender.com
ENTORNO=desarrollo                 # desarrollo | produccion

# ── Frontend (Vite) ────────────────────────────────────────
VITE_API_URL=http://localhost:8000
```

Sólo lo que empieza con `VITE_` llega al navegador. Que no aparezca ahí ninguna clave secreta.

---

## 10. Fases de construcción

Una fase por sesión de Claude Code. Cada una termina con un commit y con su criterio de aceptación verificado. **No empezar una fase sin que la anterior pase su criterio.**

### Fase 0 · Andamio

Estructura de carpetas, `docker-compose.yml` con `postgres:16`, `db/schema.sql`, `db/seed.sql`, `.env.example`, `.gitignore`, `README.md`, `CLAUDE.md`, `requirements.txt` y `package.json`.

El seed tiene que dejar cargados todos los casos raros, porque son los que rompen las pantallas: **dos eventos** (uno activo y uno cerrado), **veinte fotos** (doce aprobadas, cinco pendientes, tres rechazadas), fotos **verticales, horizontales y una panorámica**, un nombre de invitado **con acentos y ñ** y otro vacío, `subida_en` repartido a lo largo de dos horas, y **URLs reales de Cloudinary** (fotos de prueba subidas a mano) — con URLs inventadas nadie puede maquetar.

> **Acepta si:** `docker compose up -d` levanta Postgres, los dos SQL se aplican sin error y una consulta devuelve los dos eventos con sus fotos.

### Fase 1 · Backend esqueleto con datos fijos

Los **catorce endpoints** del contrato, respondiendo datos inventados a mano, con los esquemas Pydantic definitivos. Sin base, sin Cloudinary, sin lógica. CORS y el manejador de errores uniforme ya funcionando.

Es la fase más importante en términos de equipo: a partir de acá las tres interfaces se pueden construir en paralelo sin esperar al backend real.

> **Acepta si:** `/docs` lista los catorce endpoints y cada uno devuelve una respuesta con la forma exacta del contrato, incluidos los errores.

### Fase 2 · Backend real: base, modelos y autenticación

SQLAlchemy 2.0, Alembic con la primera migración equivalente a `schema.sql`, `security.py` con bcrypt y JWT, la dependencia `admin_actual`, y los endpoints de login, listado y alta de eventos con generación de las dos claves por `secrets.token_urlsafe`.

> **Acepta si:** se hace login con un administrador del seed, se crea un evento y las dos claves son distintas entre sí y no derivan del id.

### Fase 3 · Backend: fotos y pantalla

Firma de Cloudinary, registro de foto **con la verificación de que el `public_id` pertenece a la carpeta del evento**, el endpoint incremental de la pantalla con sus dos comportamientos, y el límite de pedidos.

> **Acepta si:** un `public_id` de otra carpeta devuelve `PUBLIC_ID_AJENO`, y `?desde=N` devuelve sólo aprobadas con id mayor a N.

### Fase 4 · Backend: moderación y descarga

Moderación individual e idempotente, endpoint de lote, resumen de totales y descarga en ZIP por streaming.

> **Acepta si:** aprobar dos veces la misma foto no cambia nada la segunda vez, y la descarga de un evento con las veinte fotos del seed produce un ZIP que abre bien.

### Fase 5 · Frontend: base

Vite, TypeScript, Tailwind, React Router con las rutas de las tres zonas, `api/client.ts` con manejo del formato de error, `api/tipos.ts` espejando el contrato, y los componentes compartidos de `comp/`.

> **Acepta si:** las tres rutas cargan una pantalla mínima y el cliente muestra correctamente un error del backend.

### Fase 6 · Frontend: app del invitado

Los cuatro estados, `lib/comprimir.ts`, `lib/subir.ts` con progreso, `lib/dispositivo.ts`, los textos en su archivo y los casos borde de la sección 6.

> **Acepta si:** una foto de 4 MB llega a Cloudinary pesando menos de 500 KB, una foto vertical de iPhone queda derecha, y la barra de progreso avanza de verdad.

### Fase 7 · Frontend: pantalla de proyección

Los cinco estados, `useCola.ts` completo con polling incremental, precarga y espera creciente, el QR, el fondo desenfocado, pantalla completa y bloqueo de suspensión.

> **Acepta si:** corre veinte minutos sola sin parpadeos, y cortando la red sigue pasando fotos y se recupera al volver.

### Fase 8 · Frontend: panel de administración

Login, listado, alta con QR descargable, bandeja de moderación con los seis puntos de la sección 8, cierre y descarga.

> **Acepta si:** se moderan cincuenta fotos del seed en menos de dos minutos usando sólo el teclado, y `Z` deshace la última decisión.

### Fase 9 · Despliegue

Proyecto de Supabase con el esquema aplicado, web service y static site en Render, variables cargadas, CORS apuntando al dominio real, health check respondiendo.

> **Acepta si:** el recorrido completo funciona contra los servicios en línea, desde un celular real y no desde la máquina de desarrollo.

### Fase 10 · Endurecimiento y pruebas

Colección de pedidos versionada en el repo, prueba de volumen con tres mil fotos y `EXPLAIN ANALYZE`, **prueba escrita de aislamiento entre dos eventos**, revisión de que ninguna clave quedó en el repositorio, y README de instalación probado por alguien que no lo escribió.

> **Acepta si:** con el token de pantalla del evento A no aparece ni una foto del evento B, y está documentado.

---

## 11. `CLAUDE.md` — reglas permanentes del repositorio

Copiar tal cual a la raíz del proyecto:

```markdown
# Transmití tu foto

App para recibir fotos de invitados por QR, moderarlas y proyectarlas en pantalla.
Varios eventos simultáneos, aislados entre sí.

La especificación completa está en CONSTRUIR-APP.md. Ante cualquier duda de
comportamiento, ese archivo manda.

## Stack
Backend: Python 3.12, FastAPI, SQLAlchemy 2.0, Alembic, Pydantic v2.
Base: PostgreSQL en Supabase, usado SOLO como base de datos.
Imágenes: Cloudinary con subida firmada desde el navegador.
Frontend: React 18, Vite, TypeScript, Tailwind, React Router.
Deploy: Render.

## Reglas que no se rompen

1. El `id` interno de un evento NUNCA aparece en una respuesta pública.
   Hacia afuera existen `codigo_publico` (subir) y `token_pantalla` (leer).
2. `CLOUDINARY_API_SECRET` vive sólo en el backend. Jamás en una variable VITE_.
3. Ninguna pantalla habla con Supabase directamente. Todo pasa por FastAPI.
   Nada de supabase-js, PostgREST, Supabase Auth ni Supabase Storage.
4. Al registrar una foto, verificar que el `public_id` empiece con
   `eventos/{codigo_publico}/`. Sin esto se puede proyectar cualquier imagen.
5. Todas las marcas de tiempo son `timestamptz`. Nunca `timestamp` pelado.
6. Estados como `text` + `CHECK`, no ENUM.
7. Nada se borra. Rechazar es un estado, no un DELETE.
8. Moderar es idempotente.
9. No inventar endpoints fuera del contrato de CONSTRUIR-APP.md.
   Si hace falta uno nuevo, proponerlo antes de escribirlo.
10. No agregar dependencias fuera de las listadas sin justificarlo.

## Convenciones

- Código y nombres de variables en español, igual que el dominio
  (`evento`, `foto`, `pendiente`, `aprobada`).
- Los textos de interfaz van en archivos de textos, no incrustados en el JSX.
- Español rioplatense, segunda persona, frases cortas. Ningún texto de cara
  al invitado menciona palabras del sistema ("endpoint", "moderación", "servidor").
- Un commit por fase, con el número de fase en el mensaje.

## Comandos

    docker compose up -d                                  # Postgres local
    cd backend && uvicorn app.main:app --reload            # API en :8000
    cd frontend && npm run dev                             # SPA en :5173
    cd backend && alembic upgrade head                     # migraciones
    cd backend && pytest                                   # pruebas

## Trampas conocidas

- Supabase: usar la cadena del POOLER EN MODO SESIÓN. La conexión directa
  resuelve por IPv6 y falla desde Render con un error que parece de credenciales.
- Supabase gratuito: el proyecto se pausa tras alrededor de una semana sin uso.
  Entrar al panel antes de cada demo.
- Render gratuito: el servicio se duerme; el primer pedido puede tardar
  cerca de un minuto. Abrir la pantalla diez minutos antes del evento.
- Cloudinary: los parámetros firmados deben coincidir EXACTAMENTE con los
  enviados en el FormData.
- Fotos de iPhone: usar `createImageBitmap(file, {imageOrientation:'from-image'})`
  o van a aparecer acostadas en el proyector.
- Subida: usar XMLHttpRequest, no fetch, para poder leer el progreso real.
```

---

## 12. Prompts para Claude Code

### Arranque

```
Leé CONSTRUIR-APP.md completo antes de escribir nada.

Ejecutá la Fase 0 (Andamio) de la sección 10, y sólo esa fase.

Al terminar:
1. Creá CLAUDE.md con el contenido exacto de la sección 11.
2. Verificá el criterio de aceptación de la fase y mostrame el resultado.
3. Hacé un commit "fase 0: andamio".
4. Pará y esperá mi confirmación antes de seguir.
```

### Cada fase siguiente

```
Ejecutá la Fase N de CONSTRUIR-APP.md, y sólo esa fase.
Respetá el contrato de la sección 5 al pie de la letra: no agregues,
no saques ni renombres endpoints ni campos.
Al terminar, verificá el criterio de aceptación, mostrame cómo lo comprobaste,
hacé el commit y esperá mi confirmación.
```

### Si algo no cierra

```
Antes de improvisar: si algo de la especificación te resulta ambiguo o
contradictorio, preguntámelo en vez de resolverlo por tu cuenta.
```

---

## 13. Recorrido de aceptación final

El sistema está terminado cuando esto se puede hacer de punta a punta, contra los servicios en línea, sin tocar la base de datos a mano:

1. Entrar al panel y crear un evento nuevo.
2. Descargar su QR e imprimirlo.
3. Abrir la pantalla de proyección en otra máquina: aparece el QR gigante.
4. Escanear el QR con un celular ajeno al equipo y subir una foto sin que nadie explique nada.
5. Ver la foto aparecer en la bandeja de moderación en menos de diez segundos.
6. Aprobarla con la tecla `A`.
7. Verla proyectada en menos de veinte segundos.
8. Crear un segundo evento y comprobar que su pantalla no muestra nada del primero.
9. Cortar internet en la máquina de la proyección un minuto: la pantalla sigue pasando fotos y se recupera sola.
10. Cerrar el evento y descargar el ZIP con todas las fotos.

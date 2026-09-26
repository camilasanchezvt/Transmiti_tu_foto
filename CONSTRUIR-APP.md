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
| Íconos | `@heroicons/react` | Autorizado por pedido de la usuaria (26-sep-2026). Outline 24 para la mayoría, solid para acciones principales, mini 20 para chips y botones chicos. El ícono acompaña al texto, no lo reemplaza |
| Despliegue | **Render**: un web service para la API, un static site para el frontend | |
| Autenticación | JWT propio (`pyjwt`) + `passlib[bcrypt]` | Sólo para el administrador |

### Reglas de stack que no se negocian

- **Supabase se usa únicamente como PostgreSQL.** Nada de `supabase-js`, PostgREST, Supabase Auth ni Supabase Storage. Si una pantalla consulta Supabase directamente, se saltea el backend y con él las reglas de moderación y el aislamiento entre eventos.
- **La conexión a Supabase desde Render usa la cadena del pooler en modo sesión.** La conexión directa resuelve por IPv6 y falla desde Render con un error de red que parece de credenciales.
- **El `CLOUDINARY_API_SECRET` nunca sale del backend.** No se importa, no se referencia, no aparece en ninguna variable `VITE_*`.
- **No se agregan librerías fuera de las listadas** sin que esté justificado en el prompt de la fase. `@heroicons/react` está en la tabla porque la usuaria lo pidió: no es un precedente para sumar otras.

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
│   │   ├── models.py            # Usuario, Evento, Foto
│   │   ├── schemas.py           # modelos Pydantic de entrada y salida
│   │   ├── security.py          # hash de contraseñas, crear y validar JWT
│   │   ├── deps.py              # usuario_actual, solo_admin, es_admin, es_superadmin, evento_del_usuario, evento_por_codigo, evento_por_token
│   │   ├── errores.py           # ErrorApp y códigos
│   │   ├── ratelimit.py         # límite de pedidos en memoria (por IP, evento y celular)
│   │   ├── cloudinary_service.py# firma y armado del ZIP
│   │   └── routers/
│   │       ├── publico.py       # /api/e/*
│   │       ├── pantalla.py      # /api/pantalla/*
│   │       ├── admin.py         # /api/admin/* (sesión, eventos, fotos, video, descarga)
│   │       └── cuentas.py       # /api/cuentas/registro y /api/admin/cuentas
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
        │   ├── Boton.tsx        # botón grande (y claseBoton para un <Link>)
        │   ├── BotonChico.tsx   # cápsula de 44 px
        │   ├── ChipEstado.tsx   # Sin publicar · Abierto · Terminado
        │   ├── Confirmar.tsx    # diálogo modal
        │   ├── Cargando.tsx
        │   ├── MensajeError.tsx
        │   ├── Foto.tsx
        │   └── textos.ts        # los textos de estas piezas
        ├── lib/
        │   ├── comprimir.ts     # redimensionado y recompresión
        │   ├── subir.ts         # XHR a Cloudinary con progreso
        │   ├── fecha.ts         # "sábado 26 de septiembre", hoy en Argentina
        │   └── dispositivo.ts   # hash persistente del dispositivo
        ├── invitado/
        │   ├── PaginaInvitado.tsx
        │   └── textos.ts
        ├── pantalla/
        │   ├── PaginaPantalla.tsx
        │   ├── useCola.ts       # buffer, polling incremental, precarga
        │   └── QR.tsx
        └── admin/
            ├── LayoutAdmin.tsx      # barra fija y pestañas del panel
            ├── useSesion.ts         # quién tiene la sesión y con qué rol
            ├── navegacion.ts        # adónde vuelve cada "‹ Volver"
            ├── CompartirEvento.tsx  # QR, link y "Conectar la pantalla"
            ├── PiezasAcceso.tsx     # campos y avisos de Entrar y Crear cuenta
            ├── textos/              # un archivo por página, más comun.ts
            ├── PaginaLogin.tsx
            ├── PaginaRegistro.tsx   # pedir una cuenta
            ├── PaginaEventos.tsx    # eventos vigentes
            ├── PaginaHistorial.tsx  # terminados, y sin publicar de fecha pasada
            ├── PaginaCuentas.tsx    # sólo admin y superadmin
            ├── PaginaRevisar.tsx    # la bandeja: revisar fotos
            ├── PaginaAjustes.tsx    # publicar, pantalla, video, descargar, terminar
            └── useAtajos.ts
```

---

## 4. Modelo de datos

Tres tablas. El archivo `db/schema.sql` se crea exactamente así.

```sql
CREATE TABLE usuarios (
  id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  email         text NOT NULL UNIQUE,
  nombre        text NOT NULL,
  password_hash text NOT NULL,
  rol           text NOT NULL DEFAULT 'organizador'
                CHECK (rol IN ('superadmin','admin','organizador')),
  estado        text NOT NULL DEFAULT 'pendiente'
                CHECK (estado IN ('pendiente','activa','baja')),
  creado_en     timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE eventos (
  id             bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  usuario_id     bigint NOT NULL REFERENCES usuarios(id),
  nombre         text NOT NULL,
  fecha_evento   date NOT NULL,
  codigo_publico text NOT NULL UNIQUE,
  token_pantalla text NOT NULL UNIQUE,
  estado         text NOT NULL DEFAULT 'borrador'
                 CHECK (estado IN ('borrador','activo','cerrado')),
  max_fotos_por_dispositivo int NOT NULL DEFAULT 10,
  segundos_por_foto         int NOT NULL DEFAULT 7,
  creado_en      timestamptz NOT NULL DEFAULT now(),
  cerrado_en     timestamptz,
  -- El video del evento, que arma Cloudinary en segundo plano.
  video_estado    text CHECK (video_estado IN ('procesando','listo','fallo')),
  video_public_id text,
  video_url       text,
  video_fotos     int,
  video_pedido_en timestamptz
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
  moderada_por     bigint REFERENCES usuarios(id)
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
- Nada se borra: una foto rechazada sigue existiendo y se puede revertir. Una cuenta tampoco: se da de baja, y sus eventos y fotos quedan.
- `usuarios` empezó llamándose `administradores`; la migración `0003_usuarios_y_roles` la renombró, le agregó `rol` y `estado`, y pasó `eventos.admin_id` a `usuario_id`. Las cuentas que ya existían quedaron `admin` y `activa`.
- La migración `0004_superadmin` sólo amplía el `CHECK` de `rol` con `superadmin`. No promueve a nadie: el superadmin se nombra a mano (ver *Nombrar un superadmin* en la sección 5). Su downgrade vuelve a `admin` a los superadmin antes de restaurar el `CHECK` viejo.

---

## 5. Contrato de API

Base: `/api`. Todo JSON. Todos los errores tienen la misma forma:

```json
{ "error": { "codigo": "EVENTO_CERRADO", "mensaje": "Este evento ya terminó" } }
```

### Códigos de error

`EVENTO_NO_ENCONTRADO` · `EVENTO_CERRADO` · `EVENTO_BORRADOR` · `FOTO_NO_ENCONTRADA` · `ARCHIVO_INVALIDO` · `PUBLIC_ID_AJENO` · `LIMITE_ALCANZADO` · `DEMASIADOS_PEDIDOS` · `NO_AUTORIZADO` · `DATOS_INVALIDOS`

`NO_AUTORIZADO` sale con **401** cuando falta la sesión o no sirve, y con **403** cuando la sesión es válida pero no alcanza: una cuenta de baja en el login (con la contraseña correcta), un organizador en algo que es sólo de admin, o un admin sobre la cuenta de otro admin o de un superadmin. El panel usa el código HTTP para distinguirlos.

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

Dos topes de pedidos, cada 10 minutos y por evento, y hay que pasar los dos: **30 por celular** (IP + `dispositivo_hash`) y **600 por conexión** (IP). En un salón todos los invitados comparten el wifi y salen por la misma IP pública: con un tope por IP solo, a los 30 pedidos quedaba bloqueado el salón entero. El de la conexión es un techo alto contra un script que inventa un dispositivo por pedido. Un pedido frenado por uno de los dos no se anota en el otro. Además sigue valiendo el máximo de fotos por celular del evento (`LIMITE_ALCANZADO`).

**`POST /api/e/{codigo_publico}/fotos`**
```json
body → { "public_id": "eventos/ab12cd34/k3j2h1", "url": "https://res.cloudinary.com/...",
         "ancho": 1600, "alto": 1200, "bytes": 348211,
         "dispositivo_hash": "9f2c1a...", "nombre_invitado": "Sofi" }
201  → { "id": 128, "estado": "pendiente" }
400  → ARCHIVO_INVALIDO · 403 → PUBLIC_ID_AJENO · 409 → EVENTO_CERRADO · 422 → DATOS_INVALIDOS
429  → LIMITE_ALCANZADO | DEMASIADOS_PEDIDOS
```
**Verificación obligatoria:** el `public_id` recibido tiene que empezar con `eventos/{codigo_publico}/`, seguido sólo de letras, números, `_` o `-` (lo que genera Cloudinary). Si no, `PUBLIC_ID_AJENO`. Sin esta línea, cualquiera puede registrar la URL de una imagen ajena y aparece proyectada.

La `url` tiene que ser **exactamente** la que devuelve Cloudinary, sin agregados: `https://res.cloudinary.com/{cloud_name}/image/upload/v{version}/{public_id}.{jpg|jpeg|png|webp|heic}` (la versión es opcional). Una transformación en el medio (`l_fetch:`, `d_…`, `e_…`), `..`, una query o una extensión que no es de imagen → `ARCHIVO_INVALIDO`: con cualquiera de esas cosas la foto registrada muestra otra imagen que la subida.

`public_id` hasta 200 caracteres y `url` hasta 500; más largos → `DATOS_INVALIDOS`. Los mismos dos topes que la firma, en cuentas aparte: 30 por celular y 600 por conexión cada 10 minutos (`DEMASIADOS_PEDIDOS`). Hacen falta aparte porque registrar no exige haber pedido una firma, y el cupo por celular cuenta un `dispositivo_hash` que elige el cliente.

### Cuentas — registro público

**`POST /api/cuentas/registro`** — sin auth
```json
body → { "email": "bruno@ejemplo.com", "nombre": "Bruno", "password": "diez-o-mas" }
201  → { "estado": "pendiente" }
422  → DATOS_INVALIDOS · 429 → DEMASIADOS_PEDIDOS
```
Responde **siempre** lo mismo, también si el email ya existe; en ese caso no crea ni cambia nada. Así no se puede averiguar qué emails están registrados. La cuenta nace `organizador` y `pendiente`, y no puede entrar hasta que un admin la habilite. El email se guarda en minúsculas y tiene que tener formato de email; nombre de 1 a 80 caracteres; contraseña de 10 a 128. Límite: 5 pedidos por hora por IP.

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

**`POST /api/pantalla/canjear`** — sin auth
```json
body → { "codigo": "394 812" }
200  → { "token_pantalla": "64syPN4YFgbJibLfIOlrjI51R0HFlKDm" }
404  → EVENTO_NO_ENCONTRADO · 429 → DEMASIADOS_PEDIDOS
```
Canjea los seis dígitos que genera el panel (`POST /api/admin/eventos/{id}/vincular`) por el token de pantalla, para no tipear 68 caracteres con el control de una tele. El código dura 10 minutos, es de un solo uso y hay uno solo vivo por evento. Mismo error para un código inexistente, vencido o usado. Límite propio: 30 pedidos cada 10 minutos por IP.

### Administración — requieren `Authorization: Bearer <token>`

| Método y ruta | Body | Respuesta |
|---|---|---|
| `POST /api/admin/login` | `{email, password}` — sin auth | `{token, expira_en}`. Email inexistente, contraseña incorrecta o cuenta `pendiente` (aun con la contraseña correcta) → 401 `NO_AUTORIZADO`, con el mismo mensaje para los tres: el registro deja elegir la contraseña de un email nuevo, y un mensaje propio para la pendiente delataría qué emails ya existían. Contraseña correcta de una cuenta `baja` → 403 `NO_AUTORIZADO`. 429 → `DEMASIADOS_PEDIDOS`: 10 intentos cada 10 minutos por IP y 20 por email, contados antes de buscar la cuenta |
| `GET /api/admin/yo` | — | `{id, email, nombre, rol}` de la sesión. `rol`: `superadmin`, `admin` u `organizador` |
| `GET /api/admin/eventos` | query opcional: `alcance=vigentes\|historial`, `organizador={id}` | lista con `{id, nombre, fecha_evento, estado, codigo_publico, token_pantalla, segundos_por_foto, max_fotos_por_dispositivo, pendientes, aprobadas, rechazadas, organizador_id, organizador_nombre}`. Un admin o un superadmin ve todos; un organizador, sólo los suyos. Regla de medianoche: `vigentes` son los `activo` de cualquier fecha más los `borrador` con fecha de hoy en adelante, del más próximo al más lejano (un abierto de ayer queda primero); `historial`, los `cerrado` de cualquier fecha más los `borrador` de fecha pasada, del más reciente al más viejo. "Hoy" es el de Argentina (UTC−3 fijo). Sin `alcance`, todos por fecha descendente. `organizador` sólo lo respetan un admin y un superadmin |
| `POST /api/admin/eventos` | `{nombre, fecha_evento, organizador_id?}` | el evento creado, con sus dos claves y su dueño. Sin `organizador_id`, el dueño es quien lo crea. Un admin puede crearlo para otra cuenta activa (si no existe o no está activa → `DATOS_INVALIDOS`); un organizador que manda otro id → 403 `NO_AUTORIZADO` |
| `PATCH /api/admin/eventos/{id}` | `{estado?, segundos_por_foto?, max_fotos_por_dispositivo?}`, al menos uno. Segundos entre 3 y 30; fotos por invitado entre 1 y 50 | el evento actualizado |
| `GET /api/admin/eventos/{id}/fotos` | query: `estado`, `desde`, `limite` | `{fotos: [...], ultimo_id}` |
| `GET /api/admin/eventos/{id}/resumen` | — | `{pendientes, aprobadas, rechazadas}` |
| `PATCH /api/admin/fotos/{id}` | `{estado}` | `{id, estado}` |
| `POST /api/admin/fotos/lote` | `{ids: [], estado}` | `{afectadas: 12}`. Para un organizador, los ids de eventos ajenos se ignoran |
| `POST /api/admin/eventos/{id}/vincular` | — | `{codigo, expira_en}`: seis dígitos para `POST /api/pantalla/canjear`. Generar uno invalida el anterior. Un `borrador` → `EVENTO_BORRADOR` |
| `GET /api/admin/eventos/{id}/descarga` | query: `incluir=aprobadas\|todas` | archivo ZIP |
| `POST /api/admin/eventos/{id}/video` | — | 202 `{estado, url, fotos, pedido_en}`. Pide a Cloudinary (`create_slideshow`) un video 1280×720 con las aprobadas, 3 s cada una, hasta 150 repartidas en la noche. Si ya hay uno en proceso, devuelve ese. Sin aprobadas → `DATOS_INVALIDOS` |
| `GET /api/admin/eventos/{id}/video` | — | `{estado: ninguno\|procesando\|listo\|fallo, url, fotos, pedido_en}`. Mientras está `procesando` le pregunta a Cloudinary; a los 30 min sin terminar pasa a `fallo` |
| `GET /api/admin/cuentas` | — admin o superadmin — | lista con `{id, email, nombre, rol, estado, creado_en, eventos, ultimo_evento}`, superadmins incluidos: `eventos` es cuántos tiene y `ultimo_evento` la fecha del más reciente, o `null`. Pendientes primero (las más nuevas arriba), después activas y al final las de baja, cada grupo por nombre |
| `PATCH /api/admin/cuentas/{id}` | admin o superadmin. `{estado?: activa\|baja, rol?: admin\|organizador, nombre?}`, al menos uno | la cuenta, con la forma del listado. Idempotente. `pendiente` no es un valor aceptado. Quién puede cambiar qué cuenta, en la matriz de abajo. Id inexistente → `DATOS_INVALIDOS` 404 |
| `GET /api/salud` | — sin auth — | `{estado, base}` |

**Reglas de negocio**

- Un evento `cerrado` rechaza subidas nuevas pero **sigue sirviendo la pantalla**, para que las aprobadas terminen de pasar.
- Un evento `borrador` no acepta nada: ni subidas ni pantalla.
- Moderar es **idempotente**: aprobar dos veces la misma foto no rompe nada ni duplica registros.
- El límite por dispositivo se cuenta contra `dispositivo_hash`, sin pedirle datos al invitado.
- Sólo imágenes: `image/jpeg`, `image/png`, `image/webp`, `image/heic`. Nada de video.
- Una foto pertenece a un solo evento y no se puede mover.
- El endpoint de firma tiene dos topes de pedidos, cada 10 minutos y por evento: 30 por celular (IP + `dispositivo_hash`) y 600 por conexión (IP). Ver `POST /api/e/{codigo_publico}/firma`. El registro de fotos lleva los mismos dos, aparte.
- **La IP de los topes** sale de una sola función, `ratelimit.ip_del_pedido`, y **nunca es el primer valor de `X-Forwarded-For`**: ése lo escribe quien manda el pedido, y con uno inventado por pedido se evadían todos los topes (el canje de seis dígitos se podía probar por fuerza bruta). En orden: `CF-Connecting-IP` (lo pone Cloudflare, que está delante de Render, y pisa el del cliente); si no viene, el **último** valor de `X-Forwarded-For` (lo agrega el proxy); si tampoco, la IP de la conexión. El primer pedido de cada arranque deja una línea en el log con qué cabeceras llegaron (sin las IPs): después del primer deploy, y de cualquier cambio de infraestructura, confirmar ahí que dice `cf-connecting-ip=sí`.
- **Roles.** Tres: `superadmin`, `admin` y `organizador`. `superadmin` es la dueña de la app: puede todo lo que puede un admin y además gestiona a los admins. `admin` ve y gestiona todos los eventos, ve todas las cuentas y gestiona las de organizador. `organizador` ve sólo sus eventos. Para todo lo que no son cuentas, un superadmin es un admin más. Un evento o una foto de otra cuenta responden 404 (`EVENTO_NO_ENCONTRADO`, `FOTO_NO_ENCONTRADA`), igual que si no existieran: un 403 confirmaría que existen. Un organizador en un endpoint sólo de admin recibe 403 `NO_AUTORIZADO`.
- **Cuentas.** Se crean solas desde el registro, como `organizador` y `pendiente`. Ningún admin crea cuentas con contraseña ni conoce contraseñas ajenas. Dar de baja reemplaza a borrar: la cuenta no entra, pero sus eventos y fotos quedan, los admins los siguen viendo y se puede reactivar.
- La sesión se valida contra la base en cada pedido: una baja corta en el acto los tokens ya emitidos, y un cambio de rol vale desde el pedido siguiente.
- **Nadie cambia su propio rol ni su propio estado.** Así el sistema nunca se queda sin admins y nadie se bloquea solo. El nombre propio sí.
- **El rol `superadmin` no se asigna desde el panel**, ni siquiera un superadmin a otra cuenta: se nombra a mano en la base (abajo).

**Quién cambia qué cuenta** (`PATCH /api/admin/cuentas/{id}`; actor = quien pide, objetivo = la cuenta). Se decide por lo que la cuenta *es*, no por si el cambio termina tocando algo: un admin no puede ni renombrar a otro admin.

| Objetivo | Actor admin | Actor superadmin |
|---|---|---|
| Organizador, en cualquier estado (`pendiente`, `activa`, `baja`) | habilitar (`estado: activa`), dar de baja, reactivar, renombrar y hacer admin (`rol: admin`). *Habilitar como admin* es `estado: activa` + `rol: admin` en un pedido | lo mismo |
| Otro admin | 403 `NO_AUTORIZADO` "No tenés permiso para esto" | pasarlo a organizador, darlo de baja, reactivarlo y renombrarlo |
| Un superadmin (que no sea la propia cuenta) | 403 `NO_AUTORIZADO` | 403 `NO_AUTORIZADO`: nadie lo cambia desde el panel, ni otro superadmin |
| La propia cuenta: `rol` o `estado` | 422 `DATOS_INVALIDOS` "No podés cambiar tu propio rol ni tu estado" | lo mismo |
| La propia cuenta: `nombre` | se puede | se puede |
| Cualquier cuenta con `rol: superadmin` en el body | 422 `DATOS_INVALIDOS` "El rol superadmin no se asigna desde el panel" | lo mismo |

Los admins también pueden crear admins: fue una elección de la usuaria. Deshacerlo, en cambio, queda para un superadmin.

**Nombrar un superadmin.** No hay endpoint ni botón para esto, a propósito. Se hace a mano en el SQL Editor de Supabase (o con `psql` en desarrollo), sobre una cuenta que ya existe:

```sql
UPDATE usuarios SET rol = 'superadmin', estado = 'activa'
WHERE email = 'duena@ejemplo.com';
```

El email de arriba es de ejemplo. El real no se escribe en el código ni en la documentación: el repositorio es público. Si la cuenta todavía no existe, `backend/crear_admin.py` imprime el `INSERT` de una cuenta nueva y pregunta el rol (`superadmin` por defecto, o `admin`). Para sacarle el rol, lo mismo con `rol = 'admin'`.

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
| Nombre (opcional) | Tu nombre en la pantalla (si querés) |
| Error de red | No pudimos subirla. Probá de nuevo |
| Archivo inválido | Sólo podemos recibir fotos |
| Límite alcanzado | Ya mandaste tus 10 fotos. ¡Gracias! (con una sola: Ya mandaste tu foto. ¡Gracias!) |
| Muchas fotos juntas | Están llegando muchas fotos juntas. Esperá un minuto y probá de nuevo |
| Evento cerrado | Este evento ya terminó |
| El evento no abre (sin señal) | No pudimos abrir el evento. Revisá tu señal y probá de nuevo |
| Evento inexistente o sin publicar | No encontramos este evento. Si todavía no empezó, probá en un rato |

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
| Ya mandó todas las que podía | El aviso, sin botón para elegir otra: fallaría otra vez después de comprimir |
| El evento terminó mientras elegía | Pasa a la pantalla de cierre, con el nombre del evento |
| La página no abre | Botón *Probar de nuevo*, sin tener que volver a escanear |
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
| No pudo arrancar | Evento sin publicar, sin red o inexistente | Sin publicar o sin red: lo dice y vuelve a probar sola cada 30 s, sin recargar la página (recargar sin red deja la tele en la página de error del navegador). Inexistente: una tele conectada con código ofrece *Desconectar esta pantalla* |

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
- Si alguien sale de pantalla completa con Escape, que se vuelva a entrar con una tecla o un click en cualquier lado. Mientras no está completa, arriba: *Tocá la pantalla o apretá una tecla para verla completa*. Si el navegador no la soporta (iPhone, muchas teles), el aviso no aparece.
- En `/p` (la tele sin token) el verbo es **Conectar**, el mismo del panel: *Conectá esta pantalla*, y las instrucciones citan el botón del panel tal cual (*Conectar con código*). *Desconectar esta pantalla* pregunta antes: con el control remoto se aprieta sin querer, y volver a conectarla pide un código nuevo.

---

## 8. Especificación del panel de administración

Rutas `/admin/login`, `/admin/registro`, `/admin` (eventos vigentes), `/admin/historial`, `/admin/cuentas` (sólo admin y superadmin), `/admin/eventos/:id/revisar` y `/admin/eventos/:id/ajustes`. Las viejas `/moderar` y `/cierre` redirigen a `/revisar` y `/ajustes`.

`/admin/historial` acepta `?organizador={id}` para quedarse con los eventos de una cuenta (es el *Ver historial* de Cuentas); sólo cuenta para un admin o un superadmin. Desde una lista, Ajustes y Revisar fotos vuelven a esa misma lista con su filtro.

Verbos unificados en todo el panel: *Descargar* (nunca Bajar), *Crear* (nunca Armar), *Revisar fotos* (nunca Moderar en lo que se ve). Estados de un evento: *Sin publicar · Abierto · Terminado*. Fechas como se dicen: *sábado 26 de septiembre*.

### Cuentas y roles

Quien quiere usar la app pide su cuenta en `/admin/registro` y espera a que un admin la habilite. Un **organizador** ve sólo sus eventos; un **admin** ve todos, con el nombre de su organizador, y además la pestaña **Cuentas**: habilitar (también *Habilitar como admin*), dar de baja, reactivar, renombrar y hacer admin a los organizadores. La **superadmin** es la dueña de la app: todo lo del admin y además gestiona a los admins (pasarlos a organizador, darlos de baja, reactivarlos). Nadie puede cambiar su propio rol ni su estado, y a la superadmin no la toca nadie desde el panel. En Cuentas, cada uno ve sólo las acciones que el backend le permite (la matriz de la sección 5); sobre una cuenta que no puede tocar, una línea tenue explica por qué.

### Alta de evento

Nombre y fecha, nada más (un admin puede elegir además para qué cuenta es). Al crearlo, la pantalla muestra lo que se necesita de verdad: el botón grande **Publicar**, con el aviso de que el QR no funciona hasta publicarlo; el **QR descargable en PNG** para imprimir y poner en las mesas, y **Conectar la pantalla** con tres opciones explicadas: *En esta compu* (abre la ventana), *En una tele* (código de seis dígitos) y *En otra compu* (copiar el link).

La tarjeta de cada evento es liviana: nombre, fecha, estado, *Revisar fotos (N)* y *Ajustes* a la vista, y *Compartir y pantalla* plegado. Por la regla de medianoche, una fiesta abierta que pasa las 00:00 sigue en Eventos hasta que la terminen: en el historial sólo hay eventos terminados o sin publicar de fecha pasada, y ninguno necesita ese bloque. El panel (`admin/navegacion.ts`, `esDelHistorial`) replica exactamente la regla del backend para saber a qué lista vuelve cada evento.

### Revisar fotos (la bandeja de moderación)

Es la pantalla que importa: se usa tres horas seguidas, con gente esperando. **Objetivo medible: cincuenta fotos en menos de dos minutos.** De ahí salen seis decisiones.

1. **Teclado antes que mouse.** `←` `→` navegar, `A` aprobar, `R` rechazar, `Z` deshacer. Con mouse son cincuenta apuntadas y cincuenta clics; con teclado son cincuenta pulsaciones sin mover la mano.
2. **Foto grande y fila de miniaturas.** Se decide mirando la foto en grande, no la miniatura.
3. **Respuesta inmediata, confirmación después.** Al apretar `A` la foto sale de la lista al instante y se pasa a la siguiente; el pedido viaja en segundo plano. Si falla, la foto vuelve a su lugar en la lista con un aviso, **sin cambiar la foto que se está mirando**: si la de la pantalla cambiara bajo el dedo, la próxima `A` aprobaría la que se acababa de rechazar. Esperar la respuesta entre foto y foto convierte dos minutos en diez.
4. **Aprobación en lote.** Un modo *Seleccionar* por toque, sin depender de `Shift` (en el celular no hay teclado), y *Aprobar todas* con un solo pedido a `/api/admin/fotos/lote`. En una fiesta llegan ráfagas de veinte fotos casi todas buenas.
5. **Auto-refresco que no mueve la posición.** Cada 10 s se buscan las nuevas, pero no se reordena lo que se está mirando: aparece un aviso discreto — *Mostrar 12 fotos nuevas* — y se incorporan al terminar la tanda. Una lista que se reacomoda sola hace que se apruebe la foto equivocada.
6. **Contador de pendientes siempre visible**, arriba y grande. Es la única métrica que importa en vivo.

**Sin confirmaciones.** Nada de "¿estás segura?" antes de rechazar: duplica los clics de la tarea que más se repite para prevenir un error que se deshace con una tecla. La red de seguridad es `Z` (o *↶ Deshacer*, en el celular), no un cartel. Deshacer devuelve la decisión entera: después de un lote, las fotos vuelven todas a su lugar, en un solo pedido. Los pedidos de una misma foto salen **en orden**, cada uno después de que termine el anterior: con `A` y enseguida `Z` en paralelo podía quedar `aprobada` en la base y proyectándose mientras la bandeja la mostraba pendiente. La única pregunta de la bandeja es *Aprobar todas*, que manda decenas de fotos a la pantalla de un toque.

### Aislamiento del lado de la persona

El backend garantiza que las fotos no se mezclen. Lo que ninguna base de datos previene es que el moderador apruebe fotos del evento equivocado con dos pestañas abiertas. Dos cosas lo resuelven: una **barra de contexto fija** con el nombre del evento y el **nombre del evento en el título de la pestaña**. No se usan colores por evento.

### Ajustes, cierre y descarga

La página de ajustes sigue el orden del evento: antes (publicar, conectar la pantalla), durante (revisar fotos), después (video, descargar) y al final *Terminar el evento*, con confirmación.

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

# Transmití tu foto

Los invitados de un evento escanean un QR, mandan una foto desde el celular y
—después de que un moderador la aprueba— la foto aparece proyectada en la
pantalla del salón. Varios eventos a la vez, aislados entre sí.

La especificación completa está en [CONSTRUIR-APP.md](CONSTRUIR-APP.md). Las
reglas permanentes para trabajar en el repo están en [CLAUDE.md](CLAUDE.md).

**Estado: backend terminado y frontend arrancado (Fases 0 a 5).** Los 14
endpoints del contrato funcionan contra la base: autenticación, firma de
Cloudinary, registro de fotos con la verificación de carpeta, la cola
incremental de la pantalla, moderación idempotente, lote y descarga en ZIP por
streaming. La app del invitado está completa: comprime la foto en el navegador,
la sube directo a Cloudinary con progreso real y la registra. La pantalla de
proyección pasa las fotos aprobadas sola, con QR, precarga, pantalla completa y
recuperación ante cortes de red. El panel permite crear eventos con su QR
descargable, moderar con el teclado y cerrar y descargar.

Falta la Fase 9 (despliegue), que necesita cuentas de Supabase, Render y
Cloudinary, y la Fase 10 (endurecimiento y pruebas).

El frontend lee `VITE_API_URL`. Si no está definida usa `http://localhost:8000`,
así que en local anda sin configurar nada.

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

**Cuentas**, las cuatro con la contraseña `fiesta1234`:

| Email | Rol y estado | Qué ve |
|---|---|---|
| `sofia@transmitifoto.test` | superadmin, activa | lo de Ana, gestiona a los admins y puede eliminar cuentas para siempre |
| `ana@transmitifoto.test` | admin, activa | todos los eventos y la pestaña Cuentas |
| `bruno@transmitifoto.test` | organizador, activa | sólo el suyo, *Cumple de 15 de Malena*, que está en Historial |
| `carla@transmitifoto.test` | organizador, pendiente | no puede entrar hasta que un admin la habilite |

Las cuentas nuevas se piden solas en `/admin/registro` y esperan a que un admin
las habilite desde Cuentas. `backend/crear_admin.py` sólo hace falta para la
primera cuenta de una base vacía; pregunta el rol (superadmin por defecto). Para
nombrar superadmin a una cuenta existente, ver *Nombrar un superadmin* en la
sección 5 de `CONSTRUIR-APP.md`.

| Evento | Estado | Código público | Token de pantalla |
|---|---|---|---|
| Casamiento Ana y Juan | activo | `ab12cd34` | `64syPN4YFgbJibLfIOlrjI51R0HFlKDm` |
| Cumple de 15 de Malena | cerrado | `ef56gh78` | `8MX4OqECds7IhkCmlK7vub76PntouGz1` |

Fotos del evento activo: 20 (12 aprobadas, 5 pendientes, 3 rechazadas).
Fotos del evento cerrado: 4 (3 aprobadas, 1 pendiente).

Para medir la bandeja de moderación hacen falta más pendientes de las que trae
el seed. `db/seed_volumen.sql` agrega 50 al evento activo y se aplica aparte:

    docker compose exec -T db psql -U transmiti < db/seed_volumen.sql

El dispositivo `9f2c1a7b…` ya subió 8 de sus 10 fotos: alcanza con mandar dos
más para probar el `LIMITE_ALCANZADO` sin tocar la base.

Las cuatro fotos del evento cerrado tienen el cartel **EVENTO-B** quemado en la
imagen. Si alguna aparece en la pantalla del evento activo, hay una fuga entre
eventos y se ve sin mirar la base.

Rutas útiles una vez que exista el frontend:

    /e/ab12cd34                                   # invitado, evento activo
    /e/ef56gh78                                   # invitado, evento cerrado
    /p                                            # pantalla sin token: pide 6 dígitos
    /p/64syPN4YFgbJibLfIOlrjI51R0HFlKDm           # pantalla, evento activo
    /p/8MX4OqECds7IhkCmlK7vub76PntouGz1           # pantalla, evento cerrado
    /admin/login                                  # panel
    /admin/registro                               # pedir una cuenta
    /admin/olvide                                 # olvidé mi contraseña
    /admin/restablecer#token=...                  # el link del email
    /admin/cuenta                                 # Mi cuenta
    /admin                                        # eventos vigentes
    /admin/historial                              # terminados o de fecha pasada
    /admin/cuentas                                # sólo admin

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

## Recuperar la contraseña por email (Brevo)

*Olvidé mi contraseña* manda un link por email con **Brevo**. Sin configurarlo,
la app anda igual y el panel dice lo mismo que siempre, pero no sale ningún email
(en el log de Render queda `email: SIN CONFIGURAR`). Para activarlo:

1. **Crear la cuenta** en [brevo.com](https://www.brevo.com). El plan gratuito
   alcanza de sobra: son unos pocos emails por mes.
2. **Verificar el remitente.** En Brevo, *Senders, Domains & Dedicated IPs →
   Senders → Add a sender*: el email desde el que salen los mensajes (uno
   creado para la app) y el nombre *Transmití tu foto*. Brevo manda un código a
   esa casilla; hasta confirmarlo, rechaza los envíos.
3. **Crear la API key.** *SMTP & API → API Keys → Generate a new API key*. Se ve
   una sola vez: copiala en ese momento. Empieza con `xkeysib-`.
4. **Cargarla en Render.** *transmitifoto-api → Environment → Add Environment
   Variable*:
   - `BREVO_API_KEY`: la clave del paso 3.
   - `EMAIL_REMITENTE`: el email verificado en el paso 2.
   - Opcionales: `EMAIL_REMITENTE_NOMBRE` (por defecto *Transmití tu foto*) y
     `URL_PANEL`, la dirección del panel para el link (por defecto, el primer
     origen `https` de `CORS_ORIGINS`).

   Guardar reinicia el servicio. No van en `render.yaml` ni en ningún archivo
   del repositorio: la clave es secreta y nunca llega al navegador.
5. **Probar.** En `/admin/olvide`, pedir el link para una cuenta activa.

**Si no llega, revisá la carpeta de spam** (y *Promociones*, en Gmail). Un
remitente recién verificado, sin dominio propio autenticado, suele caer ahí las
primeras veces; marcarlo como *No es spam* ayuda. Si tampoco está en spam,
buscá `email:` en los logs de Render: ahí dice qué respondió Brevo (por ejemplo,
un remitente sin verificar o una clave mal copiada).

El link sirve una vez y vence en una hora; pedir otro anula el anterior.
Después de elegir la contraseña nueva se cierran todas las sesiones de la
cuenta y hay que entrar de nuevo.

## Que la API no se duerma (cron-job.org)

Render gratuito duerme la API después de 15 minutos sin pedidos, y el primero
después tarda cerca de un minuto. Un servicio gratuito externo la mantiene
despierta visitando el health check cada 10 minutos:

1. **Crear la cuenta** en [cron-job.org](https://cron-job.org). Es gratis.
2. **Crear un cronjob** (*Create cronjob*):
   - URL: `{URL de la API}/api/salud`, la misma dirección que tiene
     `VITE_API_URL` en el static site, más `/api/salud`.
   - Programación: **cada 10 minutos**.
   - Método GET, sin cabeceras ni cuerpo: `/api/salud` no pide sesión.
   - Conviene activar el aviso por email cuando falla: si la API deja de
     responder, te enterás antes del evento.
3. **Probar.** El historial del cronjob tiene que mostrar respuestas 200 con
   `{"estado":"ok","base":"ok"}`. Si dice `"base":"caida"`, la API anda pero
   Supabase no contesta (¿se pausó?).

Los datos de la cuenta de cron-job.org no van en ningún archivo del repositorio.

Tres cosas a tener en cuenta:

- **Un solo web service despierto por workspace.** Render da 750 horas
  gratuitas por mes y un servicio despierto todo el mes usa hasta 744. Si en
  el mismo workspace hay otro web service gratuito que tampoco duerme, las
  horas se acaban antes de fin de mes y Render suspende los servicios. El
  static site del panel no cuenta.
- **La limpieza de los 30 días** pasa cada 6 horas en vez de una vez por
  arranque.
- **Igual, abrí la pantalla diez minutos antes del evento.** Un deploy o un
  reinicio de Render vuelven a arrancar el servicio.

## Volver al deploy anterior

Render corre `alembic upgrade head` antes de levantar la API. Si el deploy
nuevo trajo una migración, el botón **Rollback** de Render solo no alcanza: el
código viejo no conoce la versión de la base, alembic corta con
`Can't locate revision identified by '0006_cuenta_y_recuperacion'` y la API
vieja no arranca. No se cae nada, porque Render deja viva la versión nueva,
pero tampoco podés volver.

La salida es anotar en la base la versión que conoce el código viejo, con
`alembic stamp`. No toca ninguna tabla: cambia sólo esa anotación. Los
comandos van desde tu máquina, con el venv activado, el repo en el commit
**nuevo** (el único que conoce las dos versiones) y la misma `DATABASE_URL` que
tiene Render (*transmitifoto-api → Environment*). El ejemplo es el de la 0006;
con otra migración, usá su `revision` y su `down_revision`. `alembic current`
te dice en cuál está la base.

**Volver atrás, sin perder nada:**

1. **Rollback del panel** (*transmitifoto → Events*, o un deploy manual del
   commit anterior). Va primero: el panel nuevo le pide a la API cosas que la
   vieja no tiene, y *Mi cuenta* se rompe. El panel viejo, en cambio, anda con
   la API nueva: a la API sólo se le agregaron cosas.
2. **Anotá la versión vieja:**

       cd backend && DATABASE_URL='<la de Render>' alembic stamp 0005_fotos_borradas

3. **Enseguida, Rollback de la API** (*transmitifoto-api → Events*). No dejes
   pasar tiempo entre 2 y 3: si la API nueva se reinicia en el medio (por
   ejemplo, al despertarse), ya no arranca.

Mientras corre lo viejo:

- Lo nuevo queda guardado (avatares, temas, predeterminados y estilos de
  pantalla) y vuelve con el próximo deploy.
- No hay *Olvidé mi contraseña* ni *Mi cuenta*.
- Las sesiones que se cerraron al cambiar o restablecer una contraseña vuelven a
  servir hasta que vencen (12 horas).
- Los eventos nuevos se crean con la pantalla de siempre, no con los
  predeterminados de la cuenta.

**Volver a lo nuevo**, ya corregido:

1. **Anotá la versión nueva**, justo antes de desplegar:

       cd backend && DATABASE_URL='<la de Render>' alembic stamp 0006_cuenta_y_recuperacion

2. **Desplegá la API y después el panel**, como siempre. `upgrade head` no
   tiene nada que hacer y la API arranca.

Si te olvidás del paso 1, el deploy falla con `DuplicateColumn ... already
exists` y queda viva la versión vieja, sin tocar la base: hacé el stamp y
desplegá de nuevo. Si el deploy falla por otra cosa, volvé a
`stamp 0005_fotos_borradas`: con la base anotada en 0006, la API vieja no
arranca la próxima vez que se reinicie, y en el plan gratuito eso pasa cada vez
que se despierta.

**Borrar las columnas nuevas** casi nunca hace falta: el código viejo anda con
ellas. Si igual lo querés, hacelo con lo viejo ya andando y sin un evento en
curso:

    cd backend && export DATABASE_URL='<la de Render>' && alembic stamp 0006_cuenta_y_recuperacion && alembic downgrade 0005_fotos_borradas

Se pierden los avatares (las imágenes quedan en Cloudinary), los temas, los
predeterminados, los estilos de pantalla y el historial de recuperaciones.
**Nunca con lo nuevo en marcha:** la API nueva lee esas columnas y todo daría
error, también la pantalla del salón y la subida de los invitados. Después, el
próximo deploy nuevo las vuelve a crear solo, sin stamp.

## Vincular una tele

El link de la pantalla mide 68 caracteres y no se puede tipear con un control
remoto. Para eso está el código corto: en el panel, en la tarjeta del evento,
**Compartir y pantalla → Conectar la pantalla → En una tele → Conectar con
código** genera **seis dígitos**. En la tele se abre `/p` y se cargan ahí. Dura
diez minutos y sirve una sola vez.

La tele recuerda la vinculación, así que reiniciarla no obliga a repetirla.

Aun así, para un evento de verdad el camino más confiable sigue siendo un
**cable HDMI** desde una notebook: la tele pasa a ser sólo un monitor y no
depende del wifi ni del navegador que traiga.

## Estructura

    db/          esquema y datos de desarrollo
    backend/     API FastAPI          (Fases 1 a 4)
    frontend/    SPA React            (Fases 5 a 8)

## Trampas conocidas

Están todas en [CLAUDE.md](CLAUDE.md), pero las que más tiempo hacen perder:

- **Supabase:** usar la cadena del pooler en modo sesión. La conexión directa
  resuelve por IPv6 y falla desde Render con un error que parece de credenciales.
- **Contraseña de la base con `@ : / # ? %`:** en `DATABASE_URL` va codificada
  (`@` es `%40`, `#` es `%23`, `%` es `%25`). Sin codificar, la URL se lee mal y
  la conexión falla con un error que no hace pensar en la contraseña.
- **Render gratuito:** el servicio se duerme. El ping de cron-job.org lo
  mantiene despierto (ver *Que la API no se duerma*), pero igual abrí la
  pantalla diez minutos antes del evento.

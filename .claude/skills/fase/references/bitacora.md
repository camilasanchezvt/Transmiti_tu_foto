# Bitácora de decisiones

Lo que se decidió y no está en `CONSTRUIR-APP.md`. Sin esto, cada sesión
vuelve a discutir lo mismo o rompe algo que ya se había resuelto.

Una entrada por decisión: qué se decidió, por qué, y a qué fase le importa.

---

## Ambigüedades del brief, ya resueltas

### "Los catorce endpoints" son quince rutas
**Fase 1.** La sección 5 lista 15 rutas: 3 públicas + 2 de pantalla + las 10
filas de la tabla de administración. Pero la Fase 1 dice "catorce" dos veces.

Se tomó que **`GET /api/salud` no cuenta como endpoint del contrato**: está
marcado "— sin auth —" y es un health check. Quedan 14 del contrato repartidos
en los tres routers, más `/api/salud` en `main.py`. Hay una prueba que lo fija
(`test_los_catorce_endpoints_del_contrato`).

### `EVENTO_BORRADOR` no aparece en ninguna respuesta del contrato
**Fase 3.** Está en la lista de códigos de la sección 5 pero ningún endpoint lo
devuelve. El GET público de un borrador responde 404 `EVENTO_NO_ENCONTRADO`
("un evento sin publicar no existe hacia afuera").

Se lo ubicó en **la pantalla**, apoyado en la regla de negocio "un evento
borrador no acepta nada: ni subidas ni pantalla". `GET /api/pantalla/{token}`
de un borrador devuelve `EVENTO_BORRADOR` con 404.

### La Fase 8 pide moderar 50 fotos pero el seed tiene 5 pendientes
**Fase 8. RESUELTO.** El criterio de la Fase 8 es "se moderan cincuenta fotos
del seed en menos de dos minutos", pero el seed de la Fase 0 define 20 fotos,
de las cuales 5 pendientes.

Se agregó `db/seed_volumen.sql`, que suma 50 pendientes al evento activo. Va
aparte y NO se aplica solo al levantar la base: no querés 50 pendientes cada vez
que arrancás a trabajar. `db/seed.sql` queda tal cual lo describe la sección 10.

    psql -d transmiti -f db/seed_volumen.sql

---

## Datos de desarrollo

### Las URLs del seed son de la nube pública `demo` de Cloudinary
**Fases 0, 4, 7, 8.** No hay cuenta propia de Cloudinary todavía, así que el
seed no puede tener "fotos de prueba subidas a mano" como pide el brief. Las
URLs apuntan a `res.cloudinary.com/demo/...` y funcionan de verdad: las 24 se
verificaron una por una, y las columnas `ancho`, `alto` y `bytes` coinciden con
lo que devuelve cada URL.

El `public_id`, en cambio, sigue la convención del sistema
(`eventos/{codigo_publico}/…`) para que la regla 4 sea comprobable. **No
coincide** con el public_id real dentro de `demo`.

**Consecuencia para la Fase 4:** el ZIP se arma descargando `url`, nunca
resolviendo `public_id` contra la cuenta propia de Cloudinary. Ya está hecho así.

### El evento cerrado del seed lleva el cartel EVENTO-B quemado
**Fase 10.** Sus cuatro fotos tienen "EVENTO-B" dibujado encima por Cloudinary.
Si alguna aparece en la pantalla del evento activo, hay una fuga entre eventos y
se ve sin mirar la base.

Cuidado con el desplazamiento del overlay: `y_-420` está medido para fotos de
1200 px de alto. En una panorámica de 600 px el texto se va del lienzo y
Cloudinary **agranda la imagen** en vez de recortar, con lo cual las columnas
`ancho`/`alto` dejan de describir lo que devuelve la URL. Se usa
`g_north,y_60`, que entra en cualquier alto.

### El dispositivo `9f2c1a7b…` ya subió 8 de sus 10 fotos
**Fases 3 y 6.** Alcanza con mandar dos más para probar `LIMITE_ALCANZADO` sin
tocar la base.

---

## Decisiones de implementación

### Se cuentan también las rechazadas para el límite por dispositivo
**Fase 3.** El texto que ve el invitado es "Ya mandaste tus 10 fotos": se cuenta
lo que mandó, no lo que le aprobaron. Además, no contarlas dejaría mandar fotos
malas sin tope.

### El cupo se comprueba antes de firmar, no sólo al registrar
**Fase 3.** Firmar igual le entrega una firma válida a alguien que después va a
ser rechazado, y la foto queda subida a Cloudinary ocupando lugar sin figurar en
ninguna parte.

### Además del `public_id` se valida la `url`
**Fase 3.** El brief sólo pide verificar el `public_id` (regla 4), pero el campo
que después se proyecta es `url`. Con un `public_id` válido y una URL apuntando
a otra cuenta de Cloudinary, la verificación de carpeta quedaba sin efecto. La
URL tiene que ser https, de `res.cloudinary.com`, de `/image/upload/`, con
extensión de imagen y conteniendo el `public_id`.

### Un `public_id` repetido devuelve la foto que ya existe
**Fase 3.** Es el caso del navegador que reintenta después de que la primera
llamada llegó igual. "La foto llegó o no llegó, nunca queda a medias
registrada" (sección 6, casos borde).

### El ZIP se arma sobre un objeto que sólo tiene `write()`
**Fase 4.** Al no tener `seek()`, `zipfile` usa descriptores de datos y nunca
necesita retroceder, que es lo que permite ir soltando pedazos. Sin comprimir
(`ZIP_STORED`): los JPEG ya vienen comprimidos.

Las filas se leen **antes** de empezar a mandar: la sesión de base se cierra
cuando termina de resolverse la respuesta y el generador sigue corriendo
después.

### `incluir=todas` incluye las rechazadas
**Fase 4.** Se había implementado excluyéndolas y se corrigió: el brief dice
"todas o sólo las aprobadas". Una foto puede haberse rechazado por no ser buena
para proyectar y aun así los novios la quieren.

### Login: mismo error para mail inexistente que para clave incorrecta
**Fase 2.** Distinguirlos permitiría averiguar qué direcciones están
registradas. No lo pide el brief.

### La configuración se niega a arrancar en producción con el secreto de desarrollo
**Fase 2.** El `JWT_SECRET` por defecto está escrito en el repositorio, o sea
que es público. Si `ENTORNO=produccion`, la app falla al arrancar si el secreto
es el de desarrollo, si tiene menos de 32 caracteres, o si falta
`CLOUDINARY_API_SECRET`. Es preferible que Render no levante el servicio antes
que servir un panel donde cualquiera puede firmarse un token de administrador.

### `connect_timeout` de 5 segundos en el motor de base
**Fase 2.** Sin él, un host que no contesta deja el pedido colgado hasta que se
rinde TCP, más de un minuto en Windows. Apareció de verdad corriendo las
pruebas. Pasa cuando Supabase gratuito se pausó y cuando la cadena apunta a la
conexión directa y el nombre resuelve por IPv6.

### `/api/salud` responde 200 aunque la base esté caída
**Fase 2.** Con `base` en `"caida"`. Si devolviera error, Render reiniciaría el
servicio en loop por un problema que no es del servicio: cuando Supabase
gratuito se pausa, lo que hay que despertar es Supabase.

### Tailwind 3, no 4
**Fase 5.** La estructura de la sección 3 lista `tailwind.config.js`, que es
convención de la 3. La 4 no lo usa.

### La firma de Cloudinary se calcula con `hashlib`, sin el SDK
**Fase 3.** El SDK de Cloudinary no está en la lista de dependencias
autorizadas (regla 10) y el algoritmo son cuatro líneas: parámetros ordenados
alfabéticamente, unidos por `&`, `api_secret` pegado al final, SHA-1.

### La compresión se verificó con fotos reales, no con ruido
**Fase 6.** El primer intento de medir la compresión usó una imagen de ruido
aleatorio, que es el peor caso posible para JPEG: dio 673 KB y parecía que el
criterio no se cumplía. Con fotos de verdad de 4032x3024: 4,23 MB -> 134 KB y
4,96 MB -> 275 KB, ambas a 1600x1200. Si hay que volver a medir esto, usar
fotos, no ruido.

### La rotación EXIF se verifica mirando píxeles, no dimensiones
**Fase 6.** Chrome devuelve dimensiones ya rotadas incluso con
`imageOrientation: "none"`, así que comparar dimensiones no prueba nada. El
fixture es una imagen guardada 800x600 apaisada con una franja naranja en el
borde izquierdo y verde en el derecho, más EXIF Orientation=6. Bien rotada
queda 600x800 con la naranja ARRIBA y la verde ABAJO, y eso se comprueba
leyendo el color de dos píxeles.

### Falta probar la subida completa contra Cloudinary
**Fase 6, pendiente.** Sin cuenta de Cloudinary no se puede probar el recorrido
entero: firma -> subida -> registro. Lo que sí está verificado es la compresión
(con fotos reales), la rotación EXIF (a nivel de píxel), el rechazo de video, y
que `xhr.upload.onprogress` dispara de verdad (11 eventos crecientes con un
blob de 8 MB). Queda por confirmar en la Fase 9 que los parámetros firmados
coinciden exactamente con los del FormData.

### El polling incremental deja fotos invisibles para siempre
**Fase 7. Defecto del contrato, no de la implementación. IMPORTANTE.**

La sección 5 define `desde=N` como "las aprobadas con `id > N`". Pero una foto
que estaba pendiente tiene un id MENOR que el de las que se aprobaron después.
Si el moderador la aprueba más tarde, `desde=ultimo_id` no la devuelve nunca y
esa foto no se proyecta jamás.

Medido con los datos de desarrollo: el arranque en frío deja `ultimo_id` en 18
y quedan pendientes las fotos 14, 17, 19 y 20. Aprobar la 14 o la 17 no las
hace aparecer. **Es la mitad de las pendientes**, y le rompe al invitado la
única promesa del producto.

Mitigado del lado de la pantalla, sin salirse del contrato: cada 5 pasadas se
pide `desde=0&limite=maximo_buffer` en vez de sólo lo nuevo, y se incorpora lo
que la pantalla todavía no tiene. Verificado: una foto aprobada fuera de orden
aparece a los 9 segundos.

**Decidido: se deja así.** No se toca el backend. El arreglo de fondo sería que
la pantalla avance por orden de moderación y no por id, pero eso cambiaría el
significado de `desde` y de `ultimo_id`, o sea el contrato de la sección 5, que
hasta acá se respetó al pie de la letra. El costo de la mitigación es un pedido
más pesado cada medio minuto, irrelevante para doscientas fotos.

Si algún día el rezago de hasta 30 segundos molesta, la palanca barata es bajar
`PASADAS_ENTRE_RESINCRONIZACIONES` de 5 a 2 en `useCola.ts`, sin tocar nada más.

### Nunca poner efectos secundarios adentro de un updater de estado
**Fase 8.** La bandeja empujaba al historial de deshacer desde adentro de un
updater de `setFotos`. React puede invocar un updater más de una vez —en
StrictMode lo hace siempre— así que cada aprobación dejaba DOS entradas en el
historial.

Se notaba recién al deshacer: después de agotar el historial real, `Z` seguía
"deshaciendo" e insertaba fotos duplicadas. Con 55 pendientes y 50 aprobaciones,
apretar Z de más llevaba el contador a 68.

Todo el trabajo se hace ahora fuera del updater, y `deshacer` además se niega a
insertar una foto que ya está en la lista.

### La librería de QR quedó resuelta
**Fases 7 y 8.** Se usa `qrcode` (npm, MIT, ~20 KB comprimidos), propuesta y
aprobada antes de escribirla como pide la regla 10. En el panel se dibuja
siempre a 1024 px y se muestra chico por CSS: el PNG que se baja tiene que
servir para imprimir, no para la pantalla.

### `qrcode` le fija el tamaño al canvas con estilos en línea
**Fuera de fase, 16-sep-2026.** `QRCode.toCanvas` escribe `style.width` y
`style.height` en píxeles, y un estilo en línea le gana a cualquier clase. En el
panel el QR de cada tarjeta se veía a 1024 px, desbordaba y tapaba el segundo
evento. En la pantalla, `w-[38vmin]` y `w-[13vmin]` quedaban anuladas y el QR se
veía a 520 y 220 px. Salió al sacar capturas para la presentación.

Ahora todo QR se dibuja con `dibujarQR` (`frontend/src/lib/qr.ts`), que borra esos
dos estilos después de dibujar: el tamaño en pantalla lo deciden las clases del
canvas. Verificado en el navegador: el del panel mide 96 px con el mapa de bits de
1024 y el de la esquina de la pantalla, 13vmin justos.

### El campo de seis dígitos de `/p` mide 12ch
**Fuera de fase, 16-sep-2026.** Con `w-[9ch]`, más `tracking-[0.2em]`, el relleno
y el borde, los seis dígitos no entraban: se cortaba el último del placeholder y,
al escribir, el texto se corría y tapaba el primero. Con `w-[12ch]` entran
«000000» y también «800 181» con espacio, medido con `scrollWidth`.

### Se agregaron DOS endpoints fuera del contrato: vinculación por código corto
**Fuera de fase. Propuesto y aprobado antes de escribirlo, como pide la regla 9.**

    POST /api/admin/eventos/{id}/vincular   (con Bearer) -> { codigo, expira_en }
    POST /api/pantalla/canjear              (sin auth)   -> { token_pantalla }

**Por qué:** el link de la pantalla mide 68 caracteres, de los cuales 32 son el
token al azar. Tipearlo con el control remoto de una tele, en un teclado en
pantalla y con la cruceta, son cinco minutos y un error de tipeo de volver a
empezar. Eso hacía inviable usar el navegador de una smart TV.

**Por qué en ese sentido y no al revés** (que la tele muestre el código y el
panel lo cargue): un control remoto tiene teclado numérico. Seis dígitos los
escribe bien; letras y símbolos no. Además así no hace falta polling.

**Por qué seis dígitos alcanzan:** el código dura 10 minutos, es de un solo uso,
hay uno solo activo por evento, y el canje tiene el límite de pedidos de
`ratelimit.py`. Con 30 intentos cada 10 minutos por IP contra un millón de
combinaciones, la probabilidad de acertar dentro de la ventana es 0,003%. Y lo
peor que se consigue con un código robado es leer las fotos APROBADAS de un
evento: no habilita a subir, ni a moderar, ni a ver las pendientes.

El estado vive en memoria (`app/vinculacion.py`), igual que `ratelimit.py` y por
las mismas razones. Un reinicio obliga a generar el código de nuevo, y como la
vinculación entera dura menos de un minuto, en la práctica no molesta.

**Ya están en la sección 5 de CONSTRUIR-APP.md** (desde el 25-sep-2026).
`tests/test_contrato.py` tiene la lista `AGREGADOS`, que es lo que hace que el
agregado sea deliberado: si aparece un endpoint que no está ni en el contrato
ni ahí, la prueba falla.

### Cómo transmitir a una tele
**Referencia.** Ordenado por confiabilidad para un evento de tres horas:

1. **Cable HDMI** desde una notebook o mini PC. Es lo que asume el brief y lo
   que no falla: la tele es sólo un monitor.
2. **Chromecast** transmitiendo la pestaña de Chrome. Sin tocar código.
3. **Duplicar pantalla (Miracast)** desde Windows. Gratis, más caprichoso.
4. **El navegador de la tele**, ahora viable gracias al código corto. Ojo: la
   pantalla usa `blur-3xl` y `backdrop-blur`, que son filtros de GPU a pantalla
   completa repintados en cada transición. Una notebook los hace sin
   despeinarse; un Fire Stick o una tele de 2019 se pueden trabar. Si aparece
   ese problema, la salida es hacer el fondo desenfocado opcional.

`requestFullscreen`, `wakeLock`, `AbortController` y `localStorage` están
escritos con `?.` y dentro de `try`: si la tele no los tiene, la pantalla
degrada en vez de romperse.

### Cuentas y roles: admin y organizador
**Fuera de fase, 25-sep-2026.** `administradores` pasó a `usuarios` con `rol`
(`admin`, `organizador`) y `estado` (`pendiente`, `activa`, `baja`), y
`eventos.admin_id` a `usuario_id` (migración `0003_usuarios_y_roles`). Cuatro
endpoints nuevos, en la sección 5 y en `AGREGADOS`: registro, `yo`, y listar y
cambiar cuentas. Lo que se decidió:

- **Baja en vez de borrar.** Una cuenta no se borra: pasa a `baja`, no entra,
  sus eventos y fotos quedan y un admin la puede reactivar. Es la regla 7
  llevada a las cuentas. Desde el 26-sep tiene una excepción, sólo para
  superadmins: ver *Eliminar una cuenta para siempre*, más abajo.
- **El registro no revela emails.** Responde siempre `201 {"estado":"pendiente"}`
  y, si el email existe, no toca nada. El hash se calcula antes de mirar si
  existe, para que el tiempo de respuesta tampoco lo delate. Con el mismo
  criterio, el login con un email inexistente compara contra un hash de relleno.
- **Nadie cambia su propio rol ni su estado.** Así nunca se queda el sistema
  sin admins y nadie se bloquea solo. El nombre propio sí se puede cambiar.
- **404 para lo ajeno, no 403.** Un organizador que pide un evento o una foto
  de otra cuenta recibe lo mismo que si no existiera: un 403 le confirmaría que
  ese id existe. El 403 queda para lo que es de admin (cuentas).
- La cuenta se relee en cada pedido, no se confía en el token: una baja corta
  las sesiones abiertas en el acto.
- "Hoy" para vigentes/historial es UTC−3 fijo y no `zoneinfo`: en Windows no
  hay base de zonas y rompe las pruebas.

En el mismo cambio, del lado del panel:

- **Sin colores por evento.** Se borró `admin/color.ts`. Lo que evita aprobar
  fotos del evento equivocado es la barra fija con el nombre y el nombre en el
  título de la pestaña.
- **"Compartir y pantalla" vive en la tarjeta de la lista**, no se duplica en
  Ajustes: Ajustes linkea a `/admin#evento-{id}`, que abre ese bloque. En el
  historial sólo lo tienen los eventos que siguen abiertos (con la regla de
  medianoche del 26-sep, ninguno del historial sigue abierto: ver abajo).
- Ajustes y Revisar fotos vuelven a la lista de origen (el historial con su
  filtro) por el `state` del link; si no hay, a la lista donde vive el evento.
- Un id que no entra en `bigint` responde `DATOS_INVALIDOS` 422 y no 500: un
  manejador de `DataError` en `main.py`.

### Superadmin, regla de medianoche y tope de firmas por celular
**Fuera de fase, 26-sep-2026.** Tres decisiones de la usuaria. Las tres están
en la sección 5 de CONSTRUIR-APP.md; acá va el porqué. Ningún endpoint nuevo.

**1. Tercer rol: `superadmin`.** Es la dueña de la app: todo lo de un admin y
además gestiona a los admins. Migración `0004_superadmin`, que sólo amplía el
`CHECK` de `usuarios.rol`.

- **No se promueve a nadie en la migración ni desde el panel.** El superadmin
  se nombra a mano con un `UPDATE` (sección 5, *Nombrar un superadmin*). El
  email real no va en el código ni en la documentación: el repositorio es
  público. `crear_admin.py` pregunta el rol, `superadmin` por defecto.
- **La matriz de `PATCH /api/admin/cuentas/{id}`:** admin y superadmin
  gestionan organizadores en cualquier estado (habilitar, baja, reactivar,
  renombrar, hacer admin); sólo un superadmin gestiona admins; al superadmin
  no lo toca nadie, ni otro superadmin (403); `rol: superadmin` en el body es
  422 siempre; lo propio sigue como antes (rol o estado 422, nombre sí).
- **Los admins también crean admins.** Lo eligió la usuaria. Deshacerlo, en
  cambio, es sólo de un superadmin: un admin no puede ni renombrar a otro.
- **El permiso se decide por lo que la cuenta es, no por el efecto del
  cambio.** Un admin que le manda a otro admin su mismo nombre recibe 403
  igual: si no, el 200 o el 403 dependerían de datos que no se ven.
- Para todo lo que no son cuentas, el superadmin es un admin más: `es_admin`
  y `solo_admin` aceptan los dos roles, y `es_superadmin` aparte se usa sólo
  en la matriz.
- El seed suma `sofia@transmitifoto.test`, superadmin, al final: las otras
  cuentas conservan sus ids.
- El downgrade de `0004` vuelve `admin` a los superadmin antes de restaurar el
  `CHECK` viejo. Siguen entrando y viendo todo; pierden sólo la gestión de admins.

**2. Regla de medianoche** (resuelve el pendiente "Una fiesta que pasa la
medianoche cae en el historial"). Vigentes = `activo` de cualquier fecha, o
`borrador` con fecha de hoy en adelante. Historial = `cerrado` de cualquier
fecha, o `borrador` de fecha pasada. Una fiesta abierta sigue en Eventos hasta
que alguien la termina, no hasta el mediodía siguiente: un corte a una hora
fija vuelve a fallar con la fiesta que se estira. Un abierto viejo que nadie
terminó queda arriba de todo en Eventos, que es justo donde hay que verlo.
"Hoy" sigue siendo UTC−3 fijo. El panel (`admin/navegacion.ts`,
`esDelHistorial`) replica la regla exacta. El listado sin `alcance` ahora
desempata por id, para que el orden no dependa de la base.

**3. Tope de firmas por celular** (resuelve el pendiente "El tope de firmas por
IP es corto para el wifi del salón"). 30 cada 10 minutos por (IP, evento,
`dispositivo_hash`) y 600 por (IP, evento). El segundo es un techo contra un
script que inventa un dispositivo por pedido: 600 firmas en diez minutos son
60 invitados mandando sus diez fotos en la misma ventana, y la mayoría de las
noches no se acerca. Si un salón grande llegara, se sube el número en
`routers/publico.py`. Las dos cuentas se anotan juntas o ninguna
(`ratelimit.permitido_en_todas`): un celular que insiste después de su tope no
le come lugar al resto del salón, y una conexión llena no le gasta la cuota a
un celular. Sigue valiendo el máximo de fotos por celular del evento. El canje
de pantalla conserva su propio tope de 30 por IP.

Además, `@heroicons/react` quedó autorizado por pedido de la usuaria (sección
2): outline 24 para la mayoría, solid para acciones principales, mini 20 para
chips y botones chicos, y el ícono acompaña al texto, no lo reemplaza.


### Borrado automático de Cloudinary a los 30 días
**Fuera de fase, 26-sep-2026.** Decisión de la usuaria. El contrato está en la
sección 5 de CONSTRUIR-APP.md (*Borrado automático a los 30 días*); acá va el
porqué. Ningún endpoint nuevo: cambian respuestas de los que ya existen.

- **30 días desde la FECHA del evento, no desde el cierre.** Es una fecha que
  se sabe desde que se crea el evento y que el panel puede anunciar siempre
  (`fotos_se_borran_el`). Desde el cierre, un evento que nadie termina no se
  borraría nunca.
- **Fotos Y video, todo.** Aprobadas, pendientes y rechazadas, y todos los
  videos (cada *Crear de nuevo* deja uno con otro public_id). Un borrado a
  medias deja archivos que nadie ve y que ocupan cupo.
- **La base no se toca.** "Nada se borra" es sobre las filas: quedan fotos,
  estados, totales e historial. Lo único nuevo es `eventos.fotos_borradas_en`
  (migración `0005_fotos_borradas`).
- **Prefijo con barra final** (`eventos/{codigo}/`). Sin ella, `eventos/ab12`
  es prefijo de `eventos/ab123...`, que es otro evento. Además
  `prefijo_del_evento` rechaza un código vacío o con caracteres raros: nunca se
  pide un borrado más ancho que una carpeta.
- **Cierre automático.** Si seguía `activo` o `borrador`, pasa a `cerrado`: una
  foto que entrara después quedaría en Cloudinary para siempre, porque el evento
  ya figura borrado. Por lo mismo el `PATCH` no deja reabrirlo (409; cerrarlo
  sí) y `_exigir_abierto` del invitado mira también
  `fotos_borradas_en`. Consecuencia buscada por la especificación: un borrador
  vencido pasa a `cerrado` y su código público deja de dar 404 para decir
  "terminó".
- **Si Cloudinary falla, no se marca y se reintenta.** Borrar lo que ya no está
  responde 200, así que repetir un borrado a medias es seguro. Una falla de un
  evento no frena a los demás de la misma pasada. El log lleva el código HTTP y
  el principio de la respuesta, nunca el secreto.
- **Paginado.** Cloudinary borra por prefijo de a mil y avisa con `next_cursor`
  o `partial`. Se repite hasta que no avise más, con un tope de 100 vueltas
  (cien mil archivos) para no quedar en un bucle si Cloudinary responde raro:
  pasado el tope es una falla y se reintenta en la próxima pasada.
- **Un evento por transacción, con `FOR NO KEY UPDATE SKIP LOCKED`.** Dos
  pasadas a la vez se reparten los eventos sin repetir ninguno. De a uno para
  que el lock dure lo que tarda un evento y un corte a mitad de pasada no pierda
  lo hecho. `NO KEY` porque el alta de una foto necesita `FOR KEY SHARE` sobre
  su evento (clave foránea), y `FOR UPDATE` a secas la dejaba esperando.
- **Tarea del lifespan, no cron.** Render gratuito no tiene cron y duerme el
  servicio: la pasada de ~60 s después de cada arranque es la que en la
  práctica borra; la de cada 6 horas cubre un servicio que no se duerme. Corre
  con `asyncio.to_thread` porque httpx y SQLAlchemy son sincrónicos.
- **`LIMPIEZA_ACTIVA`.** Sin definir, sólo en producción. Nunca sin las tres
  credenciales de Cloudinary. `tests/conftest.py` la pone en `false` antes de
  importar la app, y las pruebas llaman a `pasada_de_limpieza` a mano con
  `httpx.delete` simulado (un fixture automático hace fallar cualquier DELETE
  real).
- **`hoy_en_argentina` se mudó a `app/fechas.py`** para que la limpieza no
  dependa de un router. `routers/admin.py` la importa con el mismo nombre, así
  que las pruebas que la reemplazan en ese módulo siguen andando.
- **OJO al desplegar:** la primera pasada después del deploy borra todo evento
  con fecha de hace 30 días o más. No hay período de gracia.

### Eliminar una cuenta para siempre: la única excepción a "nada se borra"
**Fuera de fase, 26-sep-2026.** Decisión de la usuaria. El contrato está en la
sección 5 de CONSTRUIR-APP.md (fila de `DELETE /api/admin/cuentas/{id}` y
*Eliminar una cuenta para siempre*, con la matriz); acá va el porqué. Un
endpoint nuevo, en `AGREGADOS`. Sin migración: no cambia ninguna tabla.

- **Sólo un superadmin, y nunca sobre un superadmin ni sobre sí mismo.** Dar
  de baja sigue siendo lo normal para sacar a alguien. Un admin no puede ni
  sobre un organizador: es la única acción de cuentas que no comparte con el
  superadmin (dependencia `solo_superadmin`, mismo 403 y mismo mensaje que
  `solo_admin`). A un superadmin no se lo elimina desde el panel por lo mismo
  que no se lo cambia: se nombra y se saca a mano en la base. Y la propia
  cuenta no, con el criterio de siempre: nadie se bloquea solo por un clic.
- **Qué se borra: sólo la fila de `usuarios`** (nombre, email y contraseña).
  Para todo lo demás "nada se borra" sigue valiendo: eventos, fotos, videos y
  estados quedan.
- **Sus eventos pasan al superadmin que la elimina**, con fotos y videos
  (`eventos.usuario_id` = el id del superadmin). No quedan huérfanos:
  `usuario_id` es NOT NULL y cada listado y cada permiso salen del dueño. El
  superadmin ya los veía como admin; ahora figuran como suyos. Las claves
  públicas no cambian: invitados y pantalla no se enteran.
- **`fotos.moderada_por` queda en NULL** donde nombraba a la cuenta. Es una
  clave foránea sin `ON DELETE`; con NULL la foto conserva su estado y su
  `moderada_en`, y sólo se pierde quién la moderó, que era un dato de la
  persona eliminada.
- **Una sola transacción, con la fila tomada con `FOR UPDATE` primero.** Un
  evento nuevo para esa cuenta, o una foto que modera en ese momento, necesita
  `FOR KEY SHARE` sobre la misma fila (clave foránea): espera, y el DELETE
  nunca choca con una referencia que apareció a mitad de camino. Si algo falla,
  no queda nada a medias (lo prueba `test_todo_en_una_transaccion`).
- **Confirmación por email del lado del servidor.** El cuerpo trae
  `confirmar_email`, que se compara sin mayúsculas y sin espacios alrededor con
  el email de la cuenta. El diálogo del panel pide lo mismo, pero un pedido a
  mano o un panel viejo no pueden eliminar la cuenta equivocada por un id mal
  puesto. En el cuerpo y no en la URL: una URL queda en los logs de acceso.
  Por eso el DELETE lleva cuerpo, y por eso CORS ahora permite `DELETE`.
- **El permiso se mira antes que el cuerpo y que el email.** Un admin sin
  cuerpo recibe 403, no 422: a quien no puede no se le dice qué le falta.
- **Después:** el token deja de servir en el acto (`usuario_actual` ya da 401
  si la cuenta no existe) y el login responde igual que un email inexistente.
  El email queda libre para registrarse otra vez; la cuenta nueva nace
  `pendiente` y sin eventos. El id es IDENTITY y no se reusa: un token viejo
  nunca apunta a la cuenta nueva.
- **El log lleva ids, nunca emails ni nombres.** Una línea INFO que empieza con
  `cuentas:` (hijo del logger de uvicorn, como `limpieza:`): quién eliminó a
  quién y cuántos eventos pasaron. Dejar el email en el log sería conservar
  justo el dato que se acaba de borrar.
- **En el panel**, sólo la superadmin ve *Eliminar definitivamente*: rojo, sin
  fondo, al pie de la tarjeta y después de una línea, lejos de *Dar de baja*.
  El diálogo es `comp/Confirmar` con la prop nueva `aEscribir` (texto a
  escribir, etiqueta y teclado): foco inicial en el campo, confirmar
  deshabilitado hasta que lo escrito coincida con `trim().toLowerCase()` (lo
  mismo que `strip().lower()` del backend), Enter confirma sólo si coincide.
  Con campo, el diálogo va arriba en el celular para que el teclado no lo
  tape. Desde 640 px los dos botones van en fila sólo si entran con el texto
  entero; si no, se apilan. Después de eliminar, el botón de eliminar ignora
  toques durante 500 ms (la lista se corre y otra tarjeta queda bajo el dedo)
  y el foco va al título de la sección donde estaba la cuenta.
- `CLAUDE.md` sigue diciendo "7. Nada se borra." sin la excepción: no es un
  archivo de este cambio. Hay que agregarle la excepción a mano (la sección 11
  de CONSTRUIR-APP.md ya tiene el texto).

---

## Pendientes de decidir

### Docker no está instalado en la máquina de desarrollo
`docker compose up -d` es lo que documentan `CLAUDE.md` y el `README.md`, y es
el criterio de aceptación de la Fase 0. Las fases 0 a 5 se verificaron contra un
Postgres 16 portátil corriendo en `127.0.0.1:55432`, no contra Docker. El
esquema y el seed son los mismos archivos.

---

## Cómo correr las pruebas

`pytest` corre siempre. Las que necesitan Postgres se saltean solas si no está
definida `DATABASE_URL_TEST`. Para correrlas todas hay que apuntar a una base
**vacía y descartable**: el fixture borra y recrea el esquema en cada corrida.

    DATABASE_URL_TEST=postgresql+psycopg://usuario:clave@localhost:5432/transmiti_test pytest

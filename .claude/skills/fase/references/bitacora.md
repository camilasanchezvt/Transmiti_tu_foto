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
**Fase 8, pendiente.** El criterio de la Fase 8 es "se moderan cincuenta fotos
del seed en menos de dos minutos". El seed de la Fase 0 define 20 fotos, de las
cuales 5 pendientes. Va a hacer falta un seed de volumen para medirlo. **Sin
resolver.**

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

---

## Pendientes de decidir

### La librería de QR
**Fases 7 y 8.** El QR descargable en PNG y el QR de la pantalla necesitan una
librería que no está en la lista del brief. Hay que **proponerla antes de
escribirla** (regla 9). Todavía no se agregó nada.

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

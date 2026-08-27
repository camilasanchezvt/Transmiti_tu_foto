---
name: fase
description: >
  Enruta una fase de construcción de "Transmití tu foto" a las secciones exactas
  de CONSTRUIR-APP.md que hacen falta, en vez de releer las 669 líneas enteras.
  Usar al empezar cualquier fase de la 0 a la 10, al retomar el proyecto después
  de un tiempo, o antes de tocar el contrato de API, el modelo de datos o
  cualquiera de las tres interfaces. Incluye la bitácora de decisiones que ya se
  tomaron y que no están escritas en el brief.
---

# Fases de Transmití tu foto

## Qué hace esta skill

Dice **qué leer**, no **qué dice**. No copia una sola línea del contrato.

`CONSTRUIR-APP.md` es un contrato congelado y sigue siendo el que manda: "ante
cualquier duda de comportamiento, ese archivo manda" (CLAUDE.md). Si esta skill
repitiera su contenido habría dos fuentes de verdad, y la que se desactualice
primero haría más daño que el monolito.

Son 669 líneas. Cada fase necesita entre 90 y 180. Y unas 280 son redundantes
en toda sesión: la sección 11 es el `CLAUDE.md` que ya se carga solo, la 3 es la
estructura de carpetas que ya está en el disco, la 12 son los prompts de
arranque y la 1 es contexto de producto.

## Antes de empezar cualquier fase

1. Mirá el estado real: `git log --oneline` y el encabezado de `README.md`.
2. Leé `references/bitacora.md` de esta skill. Son las decisiones ya tomadas
   que el brief no tiene y que se pierden entre sesiones.
3. Leé sólo las secciones que la tabla de abajo indica para tu fase.
4. No empieces una fase sin que la anterior pase su criterio de aceptación.

Para leer una sección puntual sin traerte el archivo entero:

```bash
awk '/^## 5\./{p=1} /^## 6\./{p=0} p' CONSTRUIR-APP.md
```

## Qué leer en cada fase

| Fase | Secciones a leer |
|---|---|
| 0 · Andamio | 10 (bloque Fase 0) · 4 entera · 3 entera · 9 entera |
| 1 · Backend esqueleto | **5 entera, con Reglas de negocio** · 10 (Fase 1) · 4 (DDL + los tres identificadores) · 3 (subárbol `backend/`) |
| 2 · Base y autenticación | **4 entera** · 10 (Fase 2) · 5 (sobre de error, códigos, y las filas de login/eventos) · 9 (líneas de JWT y DATABASE_URL) |
| 3 · Fotos y pantalla | **5 (Públicos y Pantalla, con los JSON completos)** · 5 (códigos + Reglas de negocio) · 4 (eventos, fotos y los cuatro índices) · 9 (las tres líneas de CLOUDINARY) · 6 (sólo "Subida a Cloudinary") |
| 4 · Moderación y descarga | **5 (tabla de Administración)** · 5 (códigos + Reglas de negocio) · 4 (fotos + `idx_fotos_pendientes` y `idx_fotos_recientes`) · 8 (sólo "Cierre y descarga") |
| 5 · Frontend base | 5 entera salvo Reglas de negocio · 9 (bloque Frontend) · 1 (tabla de las tres interfaces) · 3 (subárbol `frontend/`) |
| 6 · App del invitado | **6 entera, con sus tres tablas** · 5 (sólo Públicos) · 5 (Reglas de negocio que tocan al invitado) |
| 7 · Pantalla de proyección | **7 entera** · 5 (bloque Pantalla + formato de error + Reglas de negocio) · 1 (tabla de interfaces y paso 7 del recorrido) |
| 8 · Panel de administración | **8 entera** · 5 (tabla de Administración entera + códigos + Reglas de negocio) · 4 (CHECK de estado y defaults) |
| 9 · Despliegue | **9 entera** · 2 (fila Despliegue + Reglas de stack) · 5 (`GET /api/salud`) · 13 entera |
| 10 · Endurecimiento | **13 entera** · 5 entera · 4 entera · 10 (Fase 10) |

En **negrita**, la sección que *es* la fase. Si sólo vas a leer una, esa.

## Criterios de aceptación

| Fase | Acepta si |
|---|---|
| 0 | Postgres levanta, los dos SQL aplican sin error y una consulta devuelve los dos eventos con sus fotos |
| 1 | `/docs` lista los catorce endpoints, cada uno con la forma exacta del contrato, **incluidos los errores** |
| 2 | Login con un administrador del seed, se crea un evento, y las dos claves son distintas entre sí y no derivan del id |
| 3 | Un `public_id` de otra carpeta devuelve `PUBLIC_ID_AJENO`, y `?desde=N` devuelve sólo aprobadas con id mayor a N |
| 4 | Aprobar dos veces la misma foto no cambia nada la segunda vez, y el ZIP de las veinte fotos del seed abre bien |
| 5 | Las tres rutas cargan una pantalla mínima y el cliente muestra correctamente un error del backend |
| 6 | Una foto de 4 MB llega a Cloudinary pesando menos de 500 KB, una vertical de iPhone queda derecha, y la barra de progreso avanza de verdad |
| 7 | Corre veinte minutos sola sin parpadeos, y cortando la red sigue pasando fotos y se recupera al volver |
| 8 | Se moderan cincuenta fotos con el teclado en menos de dos minutos, y `Z` deshace la última decisión |
| 9 | El recorrido completo funciona contra los servicios en línea, desde un celular real |
| 10 | Con el token de pantalla del evento A no aparece ni una foto del evento B, y está documentado |

## Lo que más se pasa por alto

Cosas que están enterradas donde uno no las busca:

- **El límite de 30 pedidos cada 10 minutos** vive en "Reglas de negocio" de la
  sección 5, no en la descripción de la Fase 3.
- **La regla 1 es sobre el id del EVENTO, no el de la FOTO.** El id de foto es a
  propósito y el polling incremental depende de él.
- **`intervalo_polling_ms` y `maximo_buffer` no son columnas** de la tabla
  `eventos`: son constantes del servidor. De la base sale sólo
  `segundos_por_foto`.
- **`GET /api/salud` es el único de la tabla de administración sin Bearer.** Si
  colgás toda la tabla de la misma dependencia, salud queda pidiendo token.
- **La descarga es el único endpoint que no devuelve JSON**, pese al "todo JSON"
  del encabezado de la sección 5.
- **`DATOS_INVALIDOS` y `NO_AUTORIZADO` no figuran en ninguna respuesta** del
  contrato: son el 422 de validación y el 401 del Bearer. El manejador uniforme
  tiene que atrapar `RequestValidationError` y `HTTPException` o salen como
  `{"detail": ...}` y el criterio de la Fase 1 no se cumple.

## Al cerrar una fase

1. Verificá el criterio y mostrá **cómo** lo comprobaste, no que lo comprobaste.
2. Anotá en `references/bitacora.md` toda decisión que vaya a hacer falta más
   adelante y que no esté en el brief.
3. Actualizá el encabezado de estado del `README.md`.
4. Un commit por fase, con el número de fase en el mensaje.

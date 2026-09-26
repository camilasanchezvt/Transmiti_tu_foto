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
Íconos: @heroicons/react (v2) autorizado para toda la iconografía, por pedido
de la usuaria. Nada de SVG escritos a mano ni otra librería de íconos.
Deploy: Render.

## Reglas que no se rompen

1. El `id` interno de un evento NUNCA aparece en una respuesta pública.
   Hacia afuera existen `codigo_publico` (subir) y `token_pantalla` (leer).
2. `CLOUDINARY_API_SECRET` y `BREVO_API_KEY` viven sólo en el backend. Jamás en una
   variable VITE_.
3. Ninguna pantalla habla con Supabase directamente. Todo pasa por FastAPI.
   Nada de supabase-js, PostgREST, Supabase Auth ni Supabase Storage.
4. Al registrar una foto, verificar que el `public_id` empiece con
   `eventos/{codigo_publico}/`. Sin esto se puede proyectar cualquier imagen.
5. Todas las marcas de tiempo son `timestamptz`. Nunca `timestamp` pelado.
6. Estados como `text` + `CHECK`, no ENUM.
7. Nada se borra. Rechazar es un estado, no un DELETE. Única excepción:
   un superadmin elimina una cuenta (`DELETE /api/admin/cuentas/{id}`, sección 5);
   se borra sólo su fila de `usuarios` y sus eventos pasan a él.
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
- Brevo: el remitente tiene que estar verificado en Senders o rechaza el envío.
  Sin dominio propio, los primeros emails suelen caer en spam.

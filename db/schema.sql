-- Transmití tu foto — esquema completo.
-- Se aplica automáticamente al levantar Postgres con docker compose
-- (db/ está montado en /docker-entrypoint-initdb.d, y schema.sql corre antes que seed.sql).

-- Las cuentas del panel. `superadmin` es la dueña de la app: todo lo de un
-- admin y además gestiona a los admins; se nombra a mano con un UPDATE, nunca
-- desde el panel. `admin` ve todo y gestiona organizadores; `organizador`, sólo
-- sus eventos. Se crean desde el registro público y nacen `pendiente`: no
-- entran hasta que un admin las habilita. Dar de baja es un estado, no un DELETE.
-- Única excepción: un superadmin puede eliminar una cuenta para siempre. Se
-- borra sólo su fila (y sus pedidos de recuperación, por ON DELETE CASCADE);
-- sus eventos pasan a él y fotos.moderada_por queda en NULL.
CREATE TABLE usuarios (
  id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  email         text NOT NULL UNIQUE,
  nombre        text NOT NULL,
  password_hash text NOT NULL,
  rol           text NOT NULL DEFAULT 'organizador'
                CHECK (rol IN ('superadmin','admin','organizador')),
  estado        text NOT NULL DEFAULT 'pendiente'
                CHECK (estado IN ('pendiente','activa','baja')),
  creado_en     timestamptz NOT NULL DEFAULT now(),
  -- Un token de sesión emitido antes de este momento ya no sirve. Se pone al
  -- restablecer la contraseña por email y al cambiarla desde Mi cuenta.
  sesiones_desde   timestamptz,
  -- La foto de la cuenta, en Cloudinary dentro de avatares/{id}/.
  avatar_public_id text,
  avatar_url       text,
  -- El tema del panel. 'automatico' sigue al del sistema operativo.
  tema             text NOT NULL DEFAULT 'automatico'
                   CHECK (tema IN ('oscuro','claro','automatico')),
  -- Predeterminados: se copian a cada evento nuevo de la cuenta.
  pred_segundos_por_foto         int NOT NULL DEFAULT 7
                                 CHECK (pred_segundos_por_foto BETWEEN 3 AND 30),
  pred_max_fotos_por_dispositivo int NOT NULL DEFAULT 10
                                 CHECK (pred_max_fotos_por_dispositivo BETWEEN 1 AND 50),
  pred_pantalla_fondo      text NOT NULL DEFAULT 'desenfocado'
                           CHECK (pred_pantalla_fondo IN ('desenfocado','negro')),
  pred_pantalla_transicion text NOT NULL DEFAULT 'fundido'
                           CHECK (pred_pantalla_transicion IN ('fundido','corte')),
  pred_pantalla_nombre     boolean NOT NULL DEFAULT true,
  pred_pantalla_qr         boolean NOT NULL DEFAULT true
);

-- Un evento tampoco se borra, salvo uno del Historial (terminado, o sin
-- publicar de fecha pasada) que borra un admin o un superadmin: se va con sus
-- fotos, de la base y de Cloudinary (DELETE /api/admin/eventos/{id}).
-- fotos.evento_id es la única clave foránea que apunta acá.
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
  video_pedido_en timestamptz,
  -- A los 30 días de fecha_evento se borran de Cloudinary todas las fotos y
  -- todos los videos del evento. Las filas quedan; esto marca cuándo se borraron.
  fotos_borradas_en timestamptz,
  -- Cómo se ve la pantalla del proyector. Al crear el evento se copian de los
  -- predeterminados del dueño (usuarios.pred_*).
  pantalla_fondo          text NOT NULL DEFAULT 'desenfocado'
                          CHECK (pantalla_fondo IN ('desenfocado','negro')),
  pantalla_transicion     text NOT NULL DEFAULT 'fundido'
                          CHECK (pantalla_transicion IN ('fundido','corte')),
  pantalla_mostrar_nombre boolean NOT NULL DEFAULT true,
  pantalla_mostrar_qr     boolean NOT NULL DEFAULT true
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

-- Los pedidos de "olvidé mi contraseña". Se guarda el HASH del token (sha256),
-- nunca el token: viaja sólo en el email. Sirve una vez y durante una hora; un
-- pedido nuevo anula los anteriores vivos. Nada se borra en el uso normal: se
-- van sólo con la cuenta, si un superadmin la elimina.
CREATE TABLE recuperaciones_contrasena (
  id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  usuario_id  bigint NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
  token_hash  text NOT NULL UNIQUE,
  creado_en   timestamptz NOT NULL DEFAULT now(),
  vence_en    timestamptz NOT NULL,
  usado_en    timestamptz,
  anulado_en  timestamptz
);

-- Para anular los pedidos vivos de una cuenta y para el ON DELETE CASCADE.
CREATE INDEX idx_recuperaciones_usuario ON recuperaciones_contrasena (usuario_id);

-- El índice del polling de la pantalla. Sin este, a las 200 fotos se arrastra.
CREATE INDEX idx_fotos_pantalla ON fotos (evento_id, estado, id);

-- Índice parcial: sólo las pendientes. Es el que usa la bandeja de moderación.
CREATE INDEX idx_fotos_pendientes ON fotos (evento_id, id) WHERE estado = 'pendiente';

-- Para el listado del panel, ordenado por lo más reciente.
CREATE INDEX idx_fotos_recientes ON fotos (evento_id, subida_en DESC);

-- Para contar cuántas subió un dispositivo.
CREATE INDEX idx_fotos_dispositivo ON fotos (evento_id, dispositivo_hash);

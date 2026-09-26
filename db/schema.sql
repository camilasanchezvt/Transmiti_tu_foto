-- Transmití tu foto — esquema completo.
-- Se aplica automáticamente al levantar Postgres con docker compose
-- (db/ está montado en /docker-entrypoint-initdb.d, y schema.sql corre antes que seed.sql).

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

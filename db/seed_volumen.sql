-- Datos de volumen para medir la bandeja de moderación.
--
-- El criterio de la Fase 8 es "se moderan cincuenta fotos del seed en menos de
-- dos minutos", pero el seed de la Fase 0 define veinte fotos, de las cuales
-- cinco pendientes. Este archivo agrega 50 pendientes al evento activo para
-- poder medirlo, sin tocar db/seed.sql, que sigue siendo el que describe la
-- sección 10.
--
-- Se aplica DESPUÉS de schema.sql y seed.sql:
--     psql -d transmiti -f db/seed_volumen.sql
--
-- No está en /docker-entrypoint-initdb.d a propósito: no querés 50 pendientes
-- cada vez que levantás la base para trabajar.

INSERT INTO fotos
  (evento_id, public_id, url, ancho, alto, bytes, estado,
   dispositivo_hash, nombre_invitado, subida_en)
SELECT
  (SELECT id FROM eventos WHERE codigo_publico = 'ab12cd34'),
  'eventos/ab12cd34/vol' || lpad(n::text, 3, '0'),
  'https://res.cloudinary.com/demo/image/upload/c_fill,w_'
    || (ARRAY[1600,1200,1600,1200])[1 + (n % 4)]
    || ',h_'
    || (ARRAY[1200,1600,600,1200])[1 + (n % 4)]
    || '/'
    || (ARRAY['couple','sample','balloons','woman','cld-sample','flower','bike',
              'lady','horses','cld-sample-2','coffee_cup','yellow_tulip','sheep',
              'cld-sample-3','brown_sheep','kitten_fighting','cld-sample-4',
              'nice_couple','cld-sample-5'])[1 + (n % 19)]
    || '.jpg',
  (ARRAY[1600,1200,1600,1200])[1 + (n % 4)],
  (ARRAY[1200,1600,600,1200])[1 + (n % 4)],
  100000 + n * 137,
  'pendiente',
  -- Cinco dispositivos distintos, para que el listado se parezca al de una
  -- fiesta de verdad y no al de una sola persona subiendo cincuenta veces.
  repeat(to_hex(1 + (n % 5)), 32),
  (ARRAY['Sofía','Martín Peña','Ñoño Gutiérrez','Malén Ibáñez','Agustín Iñíguez',
         '', NULL, 'Tía Coca', 'Juan', 'Ana'])[1 + (n % 10)],
  now() - (interval '1 minute' * (50 - n))
FROM generate_series(1, 50) AS n;

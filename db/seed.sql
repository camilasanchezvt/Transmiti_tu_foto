-- Transmití tu foto — datos de desarrollo.
-- Se aplica automáticamente después de schema.sql al levantar el contenedor.
--
-- CUIDADO: este archivo es SÓLO para desarrollo. Empieza truncando las tres
-- tablas para poder re-aplicarlo sin chocar con los UNIQUE. Nunca correrlo
-- contra la base de un evento real.
--
-- Cuentas (las cuatro con la contraseña fiesta1234):
--   ana@transmitifoto.test    admin, activa        ve todo: eventos y cuentas
--   bruno@transmitifoto.test  organizador, activa  ve sólo su evento
--   carla@transmitifoto.test  organizador, pendiente  no puede entrar todavía
--   sofia@transmitifoto.test  superadmin, activa   lo de Ana, y además
--                                                  gestiona a los admins
-- Sofía va última para que las otras tres conserven sus ids.
--
-- Eventos:
--   Casamiento Ana y Juan   de Ana,   activo,  hoy          (el de trabajar)
--   Cumple de 15 de Malena  de Bruno, cerrado, hace 3 días  (va al historial)
-- Las fechas son relativas a CURRENT_DATE para que el evento activo siga
-- siendo "de hoy" cada vez que se levanta la base: con una fecha fija, a la
-- semana pasaría al historial.
--
-- Sobre las imágenes: las URLs apuntan a la nube pública `demo` de Cloudinary
-- y funcionan de verdad, así que las tres pantallas se pueden maquetar contra
-- fotos reales de proporciones reales. Los `bytes` son los tamaños medidos de
-- cada URL. En cambio el `public_id` sigue la convención del sistema
-- (`eventos/{codigo_publico}/...`) y por eso NO se corresponde con el
-- public_id real dentro de la nube `demo`. Es a propósito: así el seed cumple
-- la regla 4 de CLAUDE.md y se puede probar la verificación de carpeta.
-- Consecuencia para la Fase 4: el ZIP tiene que armarse descargando `url`,
-- no resolviendo `public_id` contra la cuenta de Cloudinary propia.
--
-- Las cuatro fotos del evento cerrado llevan el cartel "EVENTO-B" quemado en
-- la imagen: si alguna se filtra a la pantalla del evento activo, se ve al
-- instante y sin mirar la base.

TRUNCATE fotos, eventos, usuarios RESTART IDENTITY CASCADE;

INSERT INTO usuarios (email, nombre, password_hash, rol, estado, creado_en) VALUES
  ('ana@transmitifoto.test', 'Ana Moderadora',
   '$2b$12$Z7n0bRZlBdFszmR/svLtZue5EPDYU0lP6WR5lKYZT9d5KCjBtrN1e',
   'admin', 'activa', now() - interval '30 days'),
  ('bruno@transmitifoto.test', 'Bruno Organizador',
   '$2b$12$bNw1doj6UF24sjtIEzW/YuQIKyZJ25EsTJEc0Cl3lOPOEcsBxnaH.',
   'organizador', 'activa', now() - interval '10 days'),
  ('carla@transmitifoto.test', 'Carla Pendiente',
   '$2b$12$il7FyjfWDmuQnwD4CvUIo.lVLZ9K.Wrcn2j52Q6cYb7Dc/X0FOOpS',
   'organizador', 'pendiente', now() - interval '2 hours'),
  ('sofia@transmitifoto.test', 'Sofía Superadmin',
   '$2b$12$f033YYQfxGcYUAjSl5qU0eF8GBazt9IX4DAB7xMD4IKE1KBKimzfy',
   'superadmin', 'activa', now() - interval '60 days');

INSERT INTO eventos
  (usuario_id, nombre, fecha_evento, codigo_publico, token_pantalla,
   estado, max_fotos_por_dispositivo, segundos_por_foto, creado_en, cerrado_en)
VALUES
  ((SELECT id FROM usuarios WHERE email = 'ana@transmitifoto.test'),
   'Casamiento Ana y Juan', CURRENT_DATE,
   'ab12cd34', '64syPN4YFgbJibLfIOlrjI51R0HFlKDm',
   'activo', 10, 7, now() - interval '3 hours', NULL),

  ((SELECT id FROM usuarios WHERE email = 'bruno@transmitifoto.test'),
   'Cumple de 15 de Malena', CURRENT_DATE - 3,
   'ef56gh78', '8MX4OqECds7IhkCmlK7vub76PntouGz1',
   'cerrado', 10, 6, now() - interval '4 days', now() - interval '3 days');

-- 20 fotos del evento activo: 12 aprobadas, 5 pendientes, 3 rechazadas.
-- Verticales, horizontales, dos cuadradas y tres panorámicas.
-- Nombres con acentos y ñ, uno vacío ('') y tres sin nombre (NULL).
-- `subida_en` repartido a lo largo de dos horas.
-- El dispositivo 9f2c1a7b… subió 8 de 10: alcanza con dos más para probar el límite.
INSERT INTO fotos
  (evento_id, public_id, url, ancho, alto, bytes, estado,
   dispositivo_hash, nombre_invitado, subida_en, moderada_en, moderada_por)
VALUES
  ((SELECT id FROM eventos WHERE codigo_publico = 'ab12cd34'),
   'eventos/ab12cd34/48cetj',
   'https://res.cloudinary.com/demo/image/upload/c_fill,w_1600,h_1200/couple.jpg',
   1600, 1200, 113420, 'aprobada', '9f2c1a7b4e8d0c35a6b8d0e2f4061835', 'Sofía',
   now() - interval '118 minutes', now() - interval '116 minutes', (SELECT id FROM usuarios WHERE email = 'ana@transmitifoto.test')),

  ((SELECT id FROM eventos WHERE codigo_publico = 'ab12cd34'),
   'eventos/ab12cd34/6nihze',
   'https://res.cloudinary.com/demo/image/upload/c_fill,w_1200,h_1600/sample.jpg',
   1200, 1600, 137408, 'aprobada', '3a5e7c9b1d2f4068ac1e3f5709b2d4f6', 'Martín Peña',
   now() - interval '112 minutes', now() - interval '110 minutes', (SELECT id FROM usuarios WHERE email = 'ana@transmitifoto.test')),

  ((SELECT id FROM eventos WHERE codigo_publico = 'ab12cd34'),
   'eventos/ab12cd34/lgcnhf',
   'https://res.cloudinary.com/demo/image/upload/c_fill,w_1600,h_600/balloons.jpg',
   1600, 600, 90317, 'aprobada', '9f2c1a7b4e8d0c35a6b8d0e2f4061835', 'Sofía',
   now() - interval '106 minutes', now() - interval '104 minutes', (SELECT id FROM usuarios WHERE email = 'ana@transmitifoto.test')),

  ((SELECT id FROM eventos WHERE codigo_publico = 'ab12cd34'),
   'eventos/ab12cd34/jcz5oh',
   'https://res.cloudinary.com/demo/image/upload/c_fill,w_1200,h_1600/woman.jpg',
   1200, 1600, 117543, 'rechazada', 'c1d3e5f7a9b02468d0e2f4061835a7c9', NULL,
   now() - interval '100 minutes', now() - interval '98 minutes', (SELECT id FROM usuarios WHERE email = 'ana@transmitifoto.test')),

  ((SELECT id FROM eventos WHERE codigo_publico = 'ab12cd34'),
   'eventos/ab12cd34/835hr8',
   'https://res.cloudinary.com/demo/image/upload/c_fill,w_1600,h_1200/cld-sample.jpg',
   1600, 1200, 204783, 'aprobada', '9f2c1a7b4e8d0c35a6b8d0e2f4061835', 'Sofía',
   now() - interval '94 minutes', now() - interval '92 minutes', (SELECT id FROM usuarios WHERE email = 'ana@transmitifoto.test')),

  ((SELECT id FROM eventos WHERE codigo_publico = 'ab12cd34'),
   'eventos/ab12cd34/dp7qg8',
   'https://res.cloudinary.com/demo/image/upload/c_fill,w_1200,h_1200/flower.jpg',
   1200, 1200, 105468, 'aprobada', '3a5e7c9b1d2f4068ac1e3f5709b2d4f6', 'Martín Peña',
   now() - interval '88 minutes', now() - interval '86 minutes', (SELECT id FROM usuarios WHERE email = 'ana@transmitifoto.test')),

  ((SELECT id FROM eventos WHERE codigo_publico = 'ab12cd34'),
   'eventos/ab12cd34/sh8jsw',
   'https://res.cloudinary.com/demo/image/upload/c_fill,w_1600,h_1200/bike.jpg',
   1600, 1200, 254442, 'pendiente', '7e1f3a5c9d2b46809f1e3d5b7a9c0e28', '',
   now() - interval '82 minutes', NULL, NULL),

  ((SELECT id FROM eventos WHERE codigo_publico = 'ab12cd34'),
   'eventos/ab12cd34/753xlq',
   'https://res.cloudinary.com/demo/image/upload/c_fill,w_1200,h_1600/lady.jpg',
   1200, 1600, 159737, 'aprobada', '9f2c1a7b4e8d0c35a6b8d0e2f4061835', 'Sofía',
   now() - interval '76 minutes', now() - interval '74 minutes', (SELECT id FROM usuarios WHERE email = 'ana@transmitifoto.test')),

  ((SELECT id FROM eventos WHERE codigo_publico = 'ab12cd34'),
   'eventos/ab12cd34/k1kp20',
   'https://res.cloudinary.com/demo/image/upload/c_fill,w_1600,h_600/horses.jpg',
   1600, 600, 139363, 'aprobada', 'c1d3e5f7a9b02468d0e2f4061835a7c9', 'Ñoño Gutiérrez',
   now() - interval '70 minutes', now() - interval '68 minutes', (SELECT id FROM usuarios WHERE email = 'ana@transmitifoto.test')),

  ((SELECT id FROM eventos WHERE codigo_publico = 'ab12cd34'),
   'eventos/ab12cd34/w43hzf',
   'https://res.cloudinary.com/demo/image/upload/c_fill,w_1200,h_1600/cld-sample-2.jpg',
   1200, 1600, 146626, 'aprobada', '3a5e7c9b1d2f4068ac1e3f5709b2d4f6', 'Martín Peña',
   now() - interval '64 minutes', now() - interval '62 minutes', (SELECT id FROM usuarios WHERE email = 'ana@transmitifoto.test')),

  ((SELECT id FROM eventos WHERE codigo_publico = 'ab12cd34'),
   'eventos/ab12cd34/ix1o47',
   'https://res.cloudinary.com/demo/image/upload/c_fill,w_1200,h_1200/coffee_cup.jpg',
   1200, 1200, 90738, 'rechazada', '9f2c1a7b4e8d0c35a6b8d0e2f4061835', 'Sofía',
   now() - interval '58 minutes', now() - interval '56 minutes', (SELECT id FROM usuarios WHERE email = 'ana@transmitifoto.test')),

  ((SELECT id FROM eventos WHERE codigo_publico = 'ab12cd34'),
   'eventos/ab12cd34/b064ta',
   'https://res.cloudinary.com/demo/image/upload/c_fill,w_1200,h_1600/yellow_tulip.jpg',
   1200, 1600, 134287, 'aprobada', '7e1f3a5c9d2b46809f1e3d5b7a9c0e28', NULL,
   now() - interval '52 minutes', now() - interval '50 minutes', (SELECT id FROM usuarios WHERE email = 'ana@transmitifoto.test')),

  ((SELECT id FROM eventos WHERE codigo_publico = 'ab12cd34'),
   'eventos/ab12cd34/ka9o34',
   'https://res.cloudinary.com/demo/image/upload/c_fill,w_1600,h_1200/sheep.jpg',
   1600, 1200, 161797, 'aprobada', '9f2c1a7b4e8d0c35a6b8d0e2f4061835', 'Sofía',
   now() - interval '46 minutes', now() - interval '44 minutes', (SELECT id FROM usuarios WHERE email = 'ana@transmitifoto.test')),

  ((SELECT id FROM eventos WHERE codigo_publico = 'ab12cd34'),
   'eventos/ab12cd34/ktb0qh',
   'https://res.cloudinary.com/demo/image/upload/c_fill,w_1600,h_1200/cld-sample-3.jpg',
   1600, 1200, 246604, 'pendiente', 'c1d3e5f7a9b02468d0e2f4061835a7c9', 'Agustín Iñíguez',
   now() - interval '40 minutes', NULL, NULL),

  ((SELECT id FROM eventos WHERE codigo_publico = 'ab12cd34'),
   'eventos/ab12cd34/qh6ldk',
   'https://res.cloudinary.com/demo/image/upload/c_fill,w_1200,h_1600/brown_sheep.jpg',
   1200, 1600, 144882, 'aprobada', '3a5e7c9b1d2f4068ac1e3f5709b2d4f6', 'Martín Peña',
   now() - interval '34 minutes', now() - interval '32 minutes', (SELECT id FROM usuarios WHERE email = 'ana@transmitifoto.test')),

  ((SELECT id FROM eventos WHERE codigo_publico = 'ab12cd34'),
   'eventos/ab12cd34/td3o29',
   'https://res.cloudinary.com/demo/image/upload/c_fill,w_1600,h_1200/kitten_fighting.jpg',
   1600, 1200, 98595, 'rechazada', '9f2c1a7b4e8d0c35a6b8d0e2f4061835', 'Sofía',
   now() - interval '28 minutes', now() - interval '26 minutes', (SELECT id FROM usuarios WHERE email = 'ana@transmitifoto.test')),

  ((SELECT id FROM eventos WHERE codigo_publico = 'ab12cd34'),
   'eventos/ab12cd34/si29bx',
   'https://res.cloudinary.com/demo/image/upload/c_fill,w_1200,h_1600/cld-sample-4.jpg',
   1200, 1600, 249215, 'pendiente', '7e1f3a5c9d2b46809f1e3d5b7a9c0e28', 'Malén Ibáñez',
   now() - interval '22 minutes', NULL, NULL),

  ((SELECT id FROM eventos WHERE codigo_publico = 'ab12cd34'),
   'eventos/ab12cd34/h6wbqg',
   'https://res.cloudinary.com/demo/image/upload/c_fill,w_1600,h_1200/nice_couple.jpg',
   1600, 1200, 116855, 'aprobada', '9f2c1a7b4e8d0c35a6b8d0e2f4061835', 'Sofía',
   now() - interval '16 minutes', now() - interval '14 minutes', (SELECT id FROM usuarios WHERE email = 'ana@transmitifoto.test')),

  ((SELECT id FROM eventos WHERE codigo_publico = 'ab12cd34'),
   'eventos/ab12cd34/wz07va',
   'https://res.cloudinary.com/demo/image/upload/c_fill,w_1600,h_600/cld-sample-5.jpg',
   1600, 600, 78466, 'pendiente', 'c1d3e5f7a9b02468d0e2f4061835a7c9', NULL,
   now() - interval '10 minutes', NULL, NULL),

  ((SELECT id FROM eventos WHERE codigo_publico = 'ab12cd34'),
   'eventos/ab12cd34/el5pp8',
   'https://res.cloudinary.com/demo/image/upload/c_fill,w_1200,h_1600/cld-sample.jpg',
   1200, 1600, 225467, 'pendiente', '3a5e7c9b1d2f4068ac1e3f5709b2d4f6', 'Martín Peña',
   now() - interval '4 minutes', NULL, NULL);

-- 4 fotos del evento cerrado (3 aprobadas, 1 pendiente).
-- Existen para poder probar el aislamiento entre eventos y la pantalla de cierre.
INSERT INTO fotos
  (evento_id, public_id, url, ancho, alto, bytes, estado,
   dispositivo_hash, nombre_invitado, subida_en, moderada_en, moderada_por)
VALUES
  ((SELECT id FROM eventos WHERE codigo_publico = 'ef56gh78'),
   'eventos/ef56gh78/g8ktrm',
   'https://res.cloudinary.com/demo/image/upload/c_fill,w_1600,h_1200/l_text:Arial_140_bold:EVENTO-B,co_white,g_north,y_60/sample.jpg',
   1600, 1200, 181950, 'aprobada', 'b4d6f8a0c2e41638507192a3b5c7d9e1', 'Malena',
   now() - interval '4380 minutes', now() - interval '4378 minutes', (SELECT id FROM usuarios WHERE email = 'bruno@transmitifoto.test')),

  ((SELECT id FROM eventos WHERE codigo_publico = 'ef56gh78'),
   'eventos/ef56gh78/2sg2xb',
   'https://res.cloudinary.com/demo/image/upload/c_fill,w_1200,h_1600/l_text:Arial_140_bold:EVENTO-B,co_white,g_north,y_60/balloons.jpg',
   1200, 1600, 163545, 'aprobada', 'b4d6f8a0c2e41638507192a3b5c7d9e1', 'Tía Coca',
   now() - interval '4360 minutes', now() - interval '4358 minutes', (SELECT id FROM usuarios WHERE email = 'bruno@transmitifoto.test')),

  ((SELECT id FROM eventos WHERE codigo_publico = 'ef56gh78'),
   'eventos/ef56gh78/1i6lop',
   'https://res.cloudinary.com/demo/image/upload/c_fill,w_1600,h_600/l_text:Arial_140_bold:EVENTO-B,co_white,g_north,y_60/flower.jpg',
   1600, 600, 82879, 'aprobada', 'b4d6f8a0c2e41638507192a3b5c7d9e1', NULL,
   now() - interval '4340 minutes', now() - interval '4338 minutes', (SELECT id FROM usuarios WHERE email = 'bruno@transmitifoto.test')),

  ((SELECT id FROM eventos WHERE codigo_publico = 'ef56gh78'),
   'eventos/ef56gh78/a1rj5p',
   'https://res.cloudinary.com/demo/image/upload/c_fill,w_1600,h_1200/l_text:Arial_140_bold:EVENTO-B,co_white,g_north,y_60/horses.jpg',
   1600, 1200, 212893, 'pendiente', 'b4d6f8a0c2e41638507192a3b5c7d9e1', 'Malena',
   now() - interval '4320 minutes', NULL, NULL);

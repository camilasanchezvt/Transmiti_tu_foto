// Todos los textos de la pantalla de proyección y de la página para conectar
// una tele. Van acá y no incrustados en el JSX, igual que los del invitado.
//
// Los leen dos públicos distintos:
//
// - Los invitados, desde lejos y de pasada. Frases de pocas palabras y nada del
//   sistema: una pared no es lugar para instrucciones.
// - Quien conecta la tele, parado frente a ella con el control en una mano y el
//   celular en la otra. Cada mensaje dice qué hacer a continuación, y los
//   nombres que cita son los de los botones del panel: así va y viene entre la
//   tele y el celular sin tener que traducir. Se importan de
//   admin/textos/compartir.ts en vez de copiarse, para que no se desincronicen
//   si allá cambia un nombre.

import { textosCompartir } from "../admin/textos/compartir";

const panel = textosCompartir.pantalla;

export const textos = {
  // ── Proyección ───────────────────────────────────────────
  pestana: (evento: string) => `${evento} · Pantalla`,
  preparando: "Preparando la pantalla…",

  esperando: "Mandá tu foto y aparece acá",
  qr: "Código para mandar tu foto",
  mandaLaTuya: "Mandá la tuya",
  gracias: "¡Gracias por las fotos!",
  llegaron: (n: number) => (n === 1 ? "Llegó una foto nueva" : `Llegaron ${n} fotos nuevas`),

  /** Sólo en el título del puntito naranja: en la pared no se lee. */
  sinConexion: "Sin conexión. Siguen pasando las fotos que ya llegaron",

  pantallaCompleta: "Tocá la pantalla o apretá una tecla para verla completa",

  // "Conectar" y no "vincular": es el verbo del panel ("Conectar la pantalla",
  // "Conectar con código").
  desconectar: "Desconectar esta pantalla",
  confirmarDesconectar: {
    titulo: "¿Desconectar esta pantalla?",
    mensaje:
      "Deja de mostrar las fotos. Para volver a conectarla vas a necesitar un código nuevo del panel.",
    confirmar: "Desconectar",
  },

  // ── Cuando la pantalla no puede arrancar ─────────────────
  // Casi siempre lo ve quien la está preparando, no los invitados.
  errores: {
    probarDeNuevo: "Probar de nuevo",
    probarAhora: "Probar ahora",

    borradorTitulo: "Este evento todavía no está publicado",
    borradorDetalle: "Cuando lo publiques desde el panel, esta pantalla arranca sola.",

    sinRedTitulo: "No pudimos conectarnos",
    sinRedDetalle: (segundos: number) =>
      // Espacio duro: que "30" y "segundos" no queden en renglones distintos.
      `Revisá el wifi. Esta pantalla vuelve a probar sola cada ${segundos}\u00a0segundos.`,

    noEncontradoTitulo: "No encontramos este evento",
    noEncontradoLink: `Revisá el link: copialo de nuevo desde el panel, en “${panel.titulo}”.`,
    noEncontradoConectada: "Desconectá esta pantalla y volvé a conectarla con un código nuevo.",

    generico: "Algo salió mal",
  },

  // ── Conectar una tele (/p) ───────────────────────────────
  conectar: {
    pestana: "Conectar pantalla · Transmití tu foto",
    titulo: "Conectá esta pantalla",
    instrucciones: `En el panel del evento, tocá “${panel.tele.boton}” y cargá acá los seis números.`,
    campo: "Código de seis números",
    boton: "Conectar",
    conectando: "Conectando…",
    vigencia: "Cada código dura diez minutos y sirve una sola vez.",

    codigoNoSirve: "Ese código no sirve o ya venció. Pedí otro en el panel.",
    demasiados: "Probaste muchas veces seguidas. Esperá unos minutos y volvé a probar.",
    sinRed: "No pudimos conectarnos. Revisá el wifi de la tele y probá de nuevo.",
  },
} as const;

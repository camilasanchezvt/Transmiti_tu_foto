// Textos de Revisar fotos (antes "Moderar").
//
// Es la pantalla que se usa tres horas seguidas, con apuro y muchas veces desde
// el celular: cada botón dice exactamente lo que hace y nada más. Lo que
// comparte con el resto del panel (Volver, Deshacer, Cancelar…) vive en
// comun.ts; acá, lo propio.
//
// Se exporta como `textosRevisar` y no como `revisar`, para no chocar con
// `comun` ni con nombres de funciones de la página.

import { comun } from "./comun";

export const textosRevisar = {
  /** Título de la pestaña. El nombre del evento va primero: con dos pestañas
   *  abiertas es lo único que las distingue en la barra del navegador. El
   *  número de pendientes adelante, como en un correo, se ve aunque la
   *  pestaña esté angosta. */
  pestana: (evento: string, pendientes: number) =>
    pendientes > 0
      ? `(${pendientes}) ${evento} · ${comun.verbos.revisarFotos}`
      : `${evento} · ${comun.verbos.revisarFotos}`,

  cargando: "Cargando las fotos…",
  noEncontrado: "No encontramos este evento",

  volver: comun.verbos.volver,
  /** "Volver a Eventos" o "Volver a Historial": a la lista de donde se vino. */
  volverA: (lista: string) => `${comun.verbos.volver} a ${lista}`,

  /** Debajo del número grande del encabezado. */
  pendientes: (n: number) => (n === 1 ? "pendiente" : "pendientes"),

  /** Texto alternativo de la foto grande. */
  foto: (nombre: string | null) => (nombre ? `Foto de ${nombre}` : "Foto sin nombre"),
  /** Para lectores de pantalla: la fila de miniaturas y cada una. */
  fila: "Fotos por revisar",
  miniatura: (posicion: number, total: number, nombre: string | null) =>
    `Foto ${posicion} de ${total}${nombre ? `, de ${nombre}` : ""}`,

  aprobar: "Aprobar",
  rechazar: "Rechazar",
  deshacer: comun.verbos.deshacer,

  // ── Selección de varias, sin Shift ────────────────────────
  seleccionar: "Seleccionar",
  tocaParaMarcar: "Tocá las fotos para marcarlas",
  seleccionadas: (n: number) => (n === 1 ? "1 seleccionada" : `${n} seleccionadas`),
  aprobarN: (n: number) => `Aprobar ${n}`,
  rechazarN: (n: number) => `Rechazar ${n}`,
  marcar: "Marcar esta foto",

  // ── Aprobar todas ─────────────────────────────────────────
  aprobarTodas: (n: number) => `Aprobar todas (${n})`,
  confirmarTodas: {
    titulo: (n: number) => `¿Aprobar las ${n} fotos?`,
    mensaje: "Van a pasar todas por la pantalla. Si te equivocás, tocá Deshacer y vuelven a la lista.",
    /** Las que llegaron mientras tanto no entran: nadie las vio todavía. */
    sinLasNuevas: (n: number) =>
      n === 1
        ? "La foto nueva que acaba de llegar no entra: revisala aparte."
        : `Las ${n} fotos nuevas que acaban de llegar no entran: revisalas aparte.`,
    confirmar: (n: number) => `Aprobar ${n}`,
  },

  /** El aviso de las que llegaron mientras se revisa. No se suman solas. */
  nuevas: (n: number) => (n === 1 ? "Mostrar 1 foto nueva" : `Mostrar ${n} fotos nuevas`),

  vacio: {
    titulo: "No hay fotos para revisar",
    texto: "Las nuevas aparecen acá solas.",
  },

  avisos: {
    fallo: "Una foto no se pudo guardar y volvió a la lista",
    falloVarias: "Las fotos no se pudieron guardar y volvieron a la lista",
    falloDeshacer: "No pudimos deshacer. Probá de nuevo",
  },

  /** La ayuda de teclado, sólo en pantallas anchas. Van sueltas porque cada
   *  tecla se dibuja aparte. */
  ayuda: {
    moverte: "moverte",
    aprobar: "aprobar",
    rechazar: "rechazar",
    deshacer: "deshacer",
    varias: "marcar varias",
    clic: "clic",
    cancelar: "cancelar la selección",
    // Los nombres de las teclas, como vienen impresos en el teclado.
    teclaShift: "Shift",
    teclaEsc: "Esc",
  },
} as const;

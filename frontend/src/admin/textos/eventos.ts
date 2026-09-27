// Textos de la página Eventos: los que están por delante, el formulario para
// crear uno y la tarjeta de cada evento. Lo que comparte con el resto del
// panel (la barra, los estados, los verbos, "Organiza …") vive en comun.ts, y
// el bloque "Compartir y pantalla" (QR, link, pantalla), en compartir.ts.
//
// Se exporta como `textosEventos` y no como `eventos`: la página ya tiene una
// lista que se llama así.

import { comun } from "./comun";

export const textosEventos = {
  titulo: comun.nav.eventos,
  cargando: "Cargando eventos…",

  crear: {
    titulo: "Crear evento",
    nombre: "Nombre",
    nombreEjemplo: "Casamiento de Ana y Juan",
    fecha: "Fecha",
    // Pista del campo vacío en iPhone, donde el navegador no muestra ninguna.
    fechaEjemplo: "dd/mm/aaaa",
    /** Una fecha de hace 30 días o más: sus fotos ya estarían vencidas. Casi
     *  siempre es el año mal puesto. Mismo texto que el backend. */
    fechaVieja: "Esa fecha ya pasó hace 30 días o más. Revisá el año",
    /** Sólo lo ve un admin: a nombre de quién queda el evento. */
    para: "Para",
    paraMi: "Mí",
    boton: comun.verbos.crear,
    error: "No pudimos crear el evento. Probá de nuevo",
  },

  vacio: {
    titulo: "No tenés eventos por delante",
    texto:
      "Creá uno arriba con el nombre y la fecha. Te damos el QR para imprimir y la pantalla lista para proyectar.",
  },

  /** Al pie de la lista, siempre: lo que ya pasó no se perdió. */
  alHistorial: "Los eventos terminados están en Historial",

  tarjeta: {
    porRevisar: (n: number) => (n === 1 ? "1 foto por revisar" : `${n} fotos por revisar`),
    revisarFotos: (n: number) =>
      n > 0 ? `${comun.verbos.revisarFotos} (${n})` : comun.verbos.revisarFotos,
    ajustes: comun.verbos.ajustes,
    publicar: comun.verbos.publicar,
    avisoSinPublicar: "El QR no funciona hasta que lo publiques",
  },

  recienCreado: {
    etiqueta: "Evento creado",
    publicarAhora: "Publicar ahora",
    publicado: "Publicado. Ya pueden mandar fotos",
    cerrar: comun.cerrar,
  },

  publicar: {
    error: "No pudimos publicarlo. Probá de nuevo",
  },
} as const;

// Textos de la página Historial: los eventos terminados y los que pasaron su
// fecha sin publicarse. Lo que comparte con el resto del panel (la barra, los estados, los
// verbos "Ajustes", "Revisar fotos", "Descargar video" y "Borrar evento", "Organiza …")
// vive en comun.ts.
//
// Se exporta como `historial` y no como `comun` para poder importar los dos en
// la misma página sin renombrar.

import { comun } from "./comun";

export const historial = {
  /** Debajo del título: a qué se viene a esta página. */
  bajada:
    "Los eventos terminados y los que pasaron su fecha sin publicarse. En Ajustes de cada uno creás el video y descargás las fotos, hasta 30 días después del evento.",

  cargando: "Cargando el historial…",

  filtro: {
    etiqueta: "Organizador",
    todos: "Todos",
    /** En el selector, para que se vea que la cuenta ya no entra. */
    deBaja: (nombre: string) => `${nombre} (de baja)`,
    /** Si el link trae una cuenta que no está en la lista (o la lista no cargó). */
    sinNombre: (id: number) => `Cuenta ${id}`,
  },

  totales: {
    aprobadas: (n: number) => (n === 1 ? "aprobada" : "aprobadas"),
    rechazadas: (n: number) => (n === 1 ? "rechazada" : "rechazadas"),
    // "Sin revisar" y no "pendientes": dice qué falta hacer, con el mismo verbo
    // que el botón de al lado. Y no cambia en singular.
    pendientes: "sin revisar",
    ninguna: "No llegó ninguna foto.",
  },

  /**
   * Cuándo se borran de Cloudinary las fotos y el video: 30 días después de la
   * fecha del evento. `fecha` ya viene escrita ("sábado 24 de octubre") y
   * `dias` es cuántos faltan. Hasta 7 días antes va en naranja y dice cuántos
   * faltan, para que se vea sin hacer la cuenta. El día del borrado (0 o
   * menos, si la limpieza todavía no pasó) ya no se pueden bajar: "se están
   * borrando", no "se borran hoy", que invitaba a descargar justo entonces.
   */
  borrado: {
    seBorran: (fecha: string) => `Se borran el ${fecha}`,
    pronto: (fecha: string, dias: number) =>
      dias <= 0 ? "Se están borrando" : dias === 1 ? "Se borran mañana" : `Se borran en ${dias} días, el ${fecha}`,
    borradas: (fecha: string) => `Fotos borradas el ${fecha}`,
  },

  descargarVideo: comun.verbos.descargarVideo,

  /** La fecha pasó y nunca se publicó. */
  nuncaPublicado: "No llegó a publicarse.",

  /** Para lectores de pantalla: "Ajustes" repetido en cada tarjeta no dice de qué evento es. */
  ajustesDe: (nombre: string) => `Ajustes de ${nombre}`,
  revisarDe: (nombre: string) => `Revisar fotos de ${nombre}`,
  descargarVideoDe: (nombre: string) => `${comun.verbos.descargarVideo} de ${nombre}`,

  /**
   * Borrar un evento para siempre: la segunda excepción a "nada se borra" (la
   * otra es eliminar una cuenta). Sólo admins y superadmins, y sólo eventos de
   * esta lista. Se confirma escribiendo el nombre del evento. Ajustes muestra
   * el mismo diálogo con estos mismos textos.
   */
  borrar: {
    accion: comun.verbos.borrarEvento,
    /** Para lectores de pantalla: "Borrar evento" repetido no dice cuál. */
    accionDe: (nombre: string) => `Borrar el evento ${nombre}`,
    titulo: (nombre: string) => `¿Borrar “${nombre}” para siempre?`,
    noSeDeshace: "No se puede deshacer.",
    /** n = las fotos que tiene; conVideo, si tiene un video listo. */
    seBorran: (n: number, conVideo: boolean) => {
      if (n === 0) return conVideo ? "Se borran el evento y el video." : "Se borra el evento. No tiene fotos.";
      const fotos = n === 1 ? "su foto" : `sus ${n} fotos`;
      return conVideo ? `Se borran el evento, ${fotos} y el video.` : `Se borran el evento y ${fotos}.`;
    },
    /** Si ya pasaron los 30 días: las fotos y el video no están desde antes. */
    yaBorradas: "Las fotos ya se habían borrado. Se borran el evento y sus datos.",
    etiqueta: "Para confirmar, escribí el nombre del evento:",
    confirmar: comun.verbos.borrarEvento,
    /** El aviso de abajo, en el Historial (también si se borró desde Ajustes). */
    hecho: "Evento borrado.",
  },

  vacio: {
    /** Un admin mirando todas las cuentas. */
    titulo: "Todavía no hay eventos terminados",
    /** Un organizador mirando los suyos. */
    tituloPropio: "Todavía no tenés eventos terminados",
    tituloDe: (nombre: string) => `${nombre} no tiene eventos terminados`,
    texto: "Cuando terminás un evento, aparece acá con sus fotos, el video y las descargas.",
    textoFiltrado: "Probá con otra cuenta o mirá los de todos.",
    irAEventos: "Ir a Eventos",
    verTodos: "Ver todos",
  },
} as const;

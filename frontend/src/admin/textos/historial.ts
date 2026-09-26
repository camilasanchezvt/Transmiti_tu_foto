// Textos de la página Historial: los eventos terminados y los que pasaron su
// fecha sin publicarse. Lo que comparte con el resto del panel (la barra, los estados, los
// verbos "Ajustes" y "Revisar fotos", "Organiza …") vive en comun.ts.
//
// Se exporta como `historial` y no como `comun` para poder importar los dos en
// la misma página sin renombrar.

export const historial = {
  /** Debajo del título: a qué se viene a esta página. */
  bajada:
    "Los eventos terminados y los que pasaron su fecha sin publicarse. En Ajustes de cada uno creás el video y descargás las fotos.",

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

  /** La fecha pasó y nunca se publicó. */
  nuncaPublicado: "No llegó a publicarse.",

  /** Para lectores de pantalla: "Ajustes" repetido en cada tarjeta no dice de qué evento es. */
  ajustesDe: (nombre: string) => `Ajustes de ${nombre}`,
  revisarDe: (nombre: string) => `Revisar fotos de ${nombre}`,

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

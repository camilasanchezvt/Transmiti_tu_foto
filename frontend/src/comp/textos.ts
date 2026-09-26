// Textos de las piezas que comparten las tres zonas: invitado, pantalla y
// panel (el botón grande, el "cargando", el error genérico, la página que no
// existe). Los lee cualquiera, así que van sin nada del panel ni del sistema.
//
// El panel los reusa desde admin/textos/comun.ts, así un "Esperá…" no se
// escribe de dos maneras.

export const textosBase = {
  esperar: "Esperá…",
  cargando: "Cargando…",
  errorGenerico: "Algo salió mal. Probá de nuevo",
  /** Cuando no hubo respuesta: el celular perdió señal o el servidor duerme. */
  sinRed: "No pudimos conectarnos. Probá de nuevo",
  probarDeNuevo: "Probar de nuevo",

  noExiste: {
    titulo: "No encontramos esta página",
    texto: "Revisá el link o escaneá el código otra vez.",
  },
} as const;

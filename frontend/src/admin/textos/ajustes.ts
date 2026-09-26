// Textos de Ajustes del evento (antes "Cierre").
//
// La página va ordenada por momento: antes, durante y después del evento, y al
// final Terminar. Quien la abre suele estar apurado y con el celular: frases
// cortas, y cada botón dice lo que hace. Los verbos compartidos (Publicar,
// Descargar, Revisar fotos, Guardar…) viven en comun.ts; acá, lo propio.

/** "45 s", "1 min", "7 min 30 s". Sin espacios que corten: la duración va
 *  dentro de un botón y en un celular no puede partirse en "7 min" / "30 s". */
function duracion(segundos: number): string {
  const nb = " ";
  if (segundos < 60) return `${segundos}${nb}s`;
  const min = Math.floor(segundos / 60);
  const resto = segundos % 60;
  return resto === 0 ? `${min}${nb}min` : `${min}${nb}min${nb}${resto}${nb}s`;
}

export const ajustes = {
  pestana: (evento: string) => `${evento} · Ajustes`,
  cargando: "Cargando el evento…",
  noEncontrado: "No encontramos este evento",
  noEncontradoDetalle: "Puede que el link esté mal o que el evento no sea tuyo.",

  // ── Antes del evento ─────────────────────────────────────
  antes: "Antes del evento",

  publicarTitulo: "Publicá el evento",
  publicarAviso:
    "Mientras no lo publiques, el QR no funciona: quien lo escanee no va a poder mandar fotos. La pantalla tampoco se puede conectar.",

  publicadoAviso: "Publicado. El QR ya recibe fotos.",

  terminadoTitulo: "El evento terminó",
  terminadoAviso:
    "No recibe fotos nuevas. La pantalla muestra el cierre y las aprobadas siguen pasando. Si lo reabrís, el QR vuelve a recibir fotos.",
  reabrir: "Reabrir",

  configTitulo: "Pantalla e invitados",
  segundos: "Segundos por foto",
  segundosAyuda: "Cuánto queda cada foto en la pantalla. La pantalla lo toma sola, sin recargarla.",
  segundosMenos: "Un segundo menos",
  segundosMas: "Un segundo más",
  cupo: "Máximo de fotos por celular",
  cupoAyuda: "Cuántas fotos puede mandar cada invitado desde su celular.",
  cupoMenos: "Una foto menos",
  cupoMas: "Una foto más",
  fueraDeRango: (min: number, max: number) => `Tiene que ser entre ${min} y ${max}.`,

  compartirTitulo: "Compartir y pantalla",
  compartirDetalle: "El QR para imprimir, el link para invitados y cómo conectar la pantalla.",

  // ── Durante el evento ────────────────────────────────────
  durante: "Durante el evento",
  fotosTitulo: "Fotos",
  pendientes: "Pendientes",
  aprobadas: "Aprobadas",
  rechazadas: "Rechazadas",
  revisarConPendientes: (n: number) => `Revisar fotos (${n})`,
  sinPendientes: "No hay fotos esperando.",
  sinFotos: "Todavía no llegó ninguna foto.",

  // ── Después del evento ───────────────────────────────────
  despues: "Después del evento",

  videoTitulo: "Video del evento",
  videoDetalle: "Las fotos aprobadas, en el orden en que llegaron, 3 segundos cada una.",
  videoMuchas: " Si hay más de 150, se eligen repartidas a lo largo del evento.",
  crearVideo: (segundos: number) => `Crear video · dura ${duracion(segundos)}`,
  crearVideoSolo: "Crear video",
  crearDeNuevo: "Crear de nuevo",
  videoSinAprobadas: "Aprobá fotos para poder crearlo.",
  videoProcesando: (fotos: number | null) =>
    `Creando el video${fotos ? ` con ${fotos} fotos` : ""}. Puede tardar unos minutos. Podés salir de esta página: cuando vuelvas va a estar acá.`,
  videoFallo: "No se pudo crear el video. Probá de nuevo.",
  videoDesactualizado: "Aprobaste fotos después de crearlo. Si querés que aparezcan, crealo de nuevo.",
  descargarVideo: "Descargar video",
  videoCargando: "Buscando el video…",

  descargaTitulo: "Descargar fotos",
  descargaDetalle: (total: string) =>
    `${total} en total. Si son muchas, el archivo tarda un rato en prepararse.`,
  descargarAprobadas: (n: number) => `Descargar las aprobadas (${n})`,
  descargarTodas: (n: number) => `Descargar todas (${n})`,
  preparando: "Preparando el archivo… no cierres esta pestaña.",
  nombreArchivo: (evento: string, fecha: string, incluir: "aprobadas" | "todas") =>
    `${evento} - ${fecha} - ${incluir}.zip`,

  // ── Terminar ─────────────────────────────────────────────
  final: "Cuando termine",
  terminarDetalle:
    "Deja de recibir fotos nuevas y la pantalla muestra el cierre. Las aprobadas siguen pasando y lo podés reabrir.",
  confirmarTitulo: "¿Terminar el evento?",
  confirmarMensaje:
    "Deja de recibir fotos nuevas. La pantalla muestra el cierre y las aprobadas siguen pasando. Si hace falta, lo podés reabrir.",
} as const;

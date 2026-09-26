// Textos del estilo de la pantalla: fondo, cambio de foto, nombre y QR.
//
// Son los mismos controles en dos lugares: los Ajustes de un evento (cambia
// ese evento) y Mi cuenta (con eso arranca cada evento nuevo). Viven acá para
// que se llamen igual en los dos, y ajustes.ts y cuenta.ts los suman con
// spread. Este archivo no importa ningún otro texto: así no hay import de ida
// y vuelta.
//
// La ayuda de fondo y de cambio de foto depende de lo elegido: dice qué va a
// ver la gente en el salón, no qué significa cada palabra.

import type { FondoPantalla, TransicionPantalla } from "../../api/tipos";

export const estiloPantalla = {
  fondo: "Fondo",
  fondoOpciones: {
    desenfocado: "Desenfocado",
    negro: "Negro",
  } satisfies Record<FondoPantalla, string>,
  fondoAyuda: {
    desenfocado: "Lo que la foto no llena, con la misma foto desenfocada.",
    negro: "Lo que la foto no llena, en negro.",
  } satisfies Record<FondoPantalla, string>,

  transicion: "Cambio de foto",
  transicionOpciones: {
    fundido: "Fundido",
    corte: "Corte",
  } satisfies Record<TransicionPantalla, string>,
  transicionAyuda: {
    fundido: "Cada foto aparece de a poco sobre la anterior.",
    corte: "Cada foto reemplaza a la anterior de golpe.",
  } satisfies Record<TransicionPantalla, string>,

  mostrarNombre: "Nombre de quien la mandó",
  mostrarNombreAyuda: "Abajo de la foto, si lo escribió.",
  mostrarQr: "QR para mandar fotos",
  mostrarQrAyuda: "Chico, en una esquina, mientras pasan las fotos.",
} as const;

// Textos del bloque "Compartir y pantalla" de cada evento: el QR para
// imprimir, el link para invitados y las tres formas de conectar la pantalla.
// Lo usan las tarjetas de Eventos y las de Historial que siguen abiertas.
//
// La pantalla (/p) cita tal cual los nombres de estos botones, para que quien
// conecta la tele vaya y venga entre la tele y el celular sin traducir: los
// importa de acá (pantalla/textos.ts), así no se desincronizan.

import { comun } from "./comun";

export const textosCompartir = {
  titulo: "Compartir y pantalla",

  qr: (nombre: string) => `QR para mandar fotos a ${nombre}`,
  descargarQR: comun.verbos.descargarQR,
  archivoQR: (nombre: string) => `QR ${nombre}.png`,
  linkInvitados: "Link para invitados",
  linkInvitadosAyuda: "Es el mismo del QR. Mandalo por WhatsApp a quien no pueda escanearlo.",
  copiar: comun.verbos.copiar,
  copiado: comun.verbos.copiado,
  /** Si el navegador no deja copiar solo, se muestra el link para copiarlo a mano. */
  copiarAMano: "Copiá este link",

  pantalla: {
    titulo: "Conectar la pantalla",
    ayuda: "Elegí dónde vas a proyectar las fotos.",
    sinPublicar: "Publicá el evento para conectar la pantalla.",
    estaCompu: {
      titulo: "En esta compu",
      ayuda: "Se abre en una ventana nueva. Llevala al proyector.",
      boton: "Abrir la pantalla",
    },
    tele: {
      titulo: "En una tele",
      ayuda: "Si la tele tiene navegador, la conectás con seis números.",
      boton: "Conectar con código",
      // "En la tele, abrí <dirección> y cargá estos números": la dirección va
      // resaltada en el medio, por eso la frase viene en dos partes.
      abri: "En la tele, abrí",
      carga: "y cargá estos números.",
      vence: (restante: string) => `Vence en ${restante}`,
      vencido: "El código venció. Pedí otro.",
      error: "No pudimos generar el código. Probá de nuevo",
      otro: "Pedir otro",
    },
    otraCompu: {
      titulo: "En otra compu",
      ayuda: "Copiá el link y abrilo en la compu del proyector.",
      boton: "Copiar link de la pantalla",
    },
  },
} as const;

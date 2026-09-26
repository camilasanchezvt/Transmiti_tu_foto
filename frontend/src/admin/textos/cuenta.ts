// Textos de Mi cuenta (/admin/cuenta): la foto y el nombre, la contraseña, el
// tema del panel y los predeterminados de cada evento nuevo. También el nombre
// oculto del avatar de la barra de arriba, que lleva acá.
//
// Los mensajes que manda el backend (contraseña actual incorrecta, demasiados
// intentos, imagen que no es de la cuenta) no se repiten: se muestran tal cual.

import type { Tema } from "../../api/tipos";
import { ayudaPassword, MAXIMO_NOMBRE, MAXIMO_PASSWORD } from "./acceso";
import { estiloPantalla } from "./estiloPantalla";

export const cuenta = {
  tituloPestana: "Mi cuenta",
  titulo: "Mi cuenta",

  /** El avatar de la barra de arriba. En el celular se ve sólo el círculo;
   *  desde sm, también el nombre. Esto va oculto después del nombre, así el
   *  lector de pantalla dice "Ana, tu cuenta" y quien maneja por voz lo
   *  encuentra diciendo el nombre que ve. La coma es a propósito. */
  enLaBarra: ", tu cuenta",

  perfil: {
    titulo: "Perfil",
    elegirFoto: "Elegir foto",
    cambiarFoto: "Cambiar foto",
    quitarFoto: "Quitar foto",
    fotoAyuda: "Se ve arriba, al lado de tu nombre, y en la lista de cuentas.",
    preparando: "Preparando la foto…",
    subiendo: (porcentaje: number) => `Subiendo la foto · ${porcentaje}%`,
    guardando: "Guardando…",
    /** Para el lector de pantalla: la barra de progreso de la subida. */
    progreso: "Progreso de la subida",
    noEsFoto: "Ese archivo no es una foto. Probá con otra.",
    noSeSubio: "No se pudo subir la foto. Revisá la conexión y probá de nuevo.",
    fotoLista: "Listo, ya tenés foto.",
    fotoQuitada: "Listo, sacamos tu foto.",

    nombre: "Tu nombre",
    nombreAyuda: "Así aparecés en el panel. Los invitados no lo ven.",
    nombreVacio: "Escribí tu nombre",
    nombreLargo: `Hasta ${MAXIMO_NOMBRE} caracteres`,
  },

  seguridad: {
    titulo: "Seguridad",
    cambiarTitulo: "Cambiar la contraseña",
    cambiarDetalle: "Vas a seguir adentro acá. En tus otros dispositivos vas a tener que entrar de nuevo.",
    actual: "Contraseña actual",
    nueva: "Contraseña nueva",
    repetir: "Repetí la nueva",
    actualVacia: "Escribí tu contraseña actual",
    /** Igual que en Crear cuenta y en Contraseña nueva: el mínimo, y cuántos
     *  faltan mientras no llega. Cumplida, el mismo texto en verde. */
    ayudaNueva: ayudaPassword,
    nuevaLarga: `Hasta ${MAXIMO_PASSWORD} caracteres`,
    repetirVacia: "Escribí la nueva otra vez",
    noCoinciden: "No coincide con la nueva",
    coinciden: "Coinciden",
    boton: "Cambiar contraseña",
    /** Arriba sigue a la vista `cambiarDetalle`: esto confirma y dice qué
     *  hacer, sin repetirlo palabra por palabra. */
    listo: "Listo, ya la cambiaste. En tus otros dispositivos, entrá con la nueva.",
    olvidaste: "¿No te acordás de la actual?",
    pedirLink: "Pedí un link por email",
  },

  apariencia: {
    titulo: "Apariencia",
    etiqueta: "Tema del panel",
    opciones: {
      oscuro: "Oscuro",
      claro: "Claro",
      automatico: "Automático",
    } satisfies Record<Tema, string>,
    ayuda: "Automático sigue al de tu celular o tu compu.",
    siempreOscuro: "La pantalla del evento y la página de los invitados se ven siempre oscuras.",
  },

  eventosNuevos: {
    titulo: "Eventos nuevos",
    explicacion: "Con esto arranca cada evento que crees. Después lo cambiás en los Ajustes de cada uno.",

    // Las mismas palabras que en los Ajustes de un evento: es el mismo número.
    segundos: "Segundos por foto",
    segundosAyuda: "Cuánto queda cada foto en la pantalla.",
    segundosMenos: "Un segundo menos",
    segundosMas: "Un segundo más",
    cupo: "Máximo de fotos por celular",
    cupoAyuda: "Cuántas fotos puede mandar cada invitado desde su celular.",
    cupoMenos: "Una foto menos",
    cupoMas: "Una foto más",
    fueraDeRango: (min: number, max: number) => `Tiene que ser entre ${min} y ${max}.`,

    pantallaTitulo: "Pantalla",
    vistaPrevia: "Así se va a ver",
    /** El nombre de ejemplo sobre la foto de la vista previa. */
    nombreDeEjemplo: "Malena",

    // Fondo, cambio de foto, nombre y QR: los mismos nombres y ayudas que en
    // los Ajustes de un evento, desde estiloPantalla.ts.
    ...estiloPantalla,
  },
} as const;

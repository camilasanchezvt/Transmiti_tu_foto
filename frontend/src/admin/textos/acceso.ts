// Textos de las páginas de acceso: Entrar, Crear cuenta, Olvidé mi contraseña
// y Contraseña nueva.
//
// Las lee gente que todavía no usó el panel (a veces es la primera vez que ve
// la app), así que van sin palabras del sistema: nada de "usuario", "sesión",
// "registro" ni "credenciales". Rioplatense, segunda persona, frases cortas.
//
// Los mensajes que manda el backend (email o contraseña incorrectos, que es
// el mismo para una cuenta que todavía no habilitaron; cuenta de baja;
// demasiados intentos) NO se repiten acá: se muestran tal cual llegan, porque
// ya están escritos para leerse así. El aviso de "esperá que te habiliten" lo
// da la confirmación de Crear cuenta (registro.exito.mensaje).

/** Lo mismo que exige el backend (PedidoRegistro y PedidoRestablecer en
 *  schemas.py). */
export const MINIMO_PASSWORD = 10;
export const MAXIMO_PASSWORD = 128;
export const MAXIMO_NOMBRE = 80;

/** La ayuda debajo de una contraseña nueva: el mínimo y cuántos faltan. La
 *  usan Crear cuenta, Contraseña nueva y el cambio de contraseña de Mi cuenta. */
export function ayudaPassword(largo: number): string {
  if (largo === 0) return `Mínimo ${MINIMO_PASSWORD} caracteres`;
  if (largo < MINIMO_PASSWORD) {
    const faltan = MINIMO_PASSWORD - largo;
    return `Mínimo ${MINIMO_PASSWORD} caracteres · te ${faltan === 1 ? "falta 1" : `faltan ${faltan}`}`;
  }
  // Cumplida: el mismo texto, en verde y con el tilde que pone el campo.
  return `Mínimo ${MINIMO_PASSWORD} caracteres`;
}

/** Los errores de email y de contraseña nueva, iguales en todas las páginas. */
const erroresEmail = {
  emailVacio: "Escribí tu email",
  emailInvalido: "Ese email no está completo. Revisalo",
};
const erroresPassword = {
  passwordLarga: `Hasta ${MAXIMO_PASSWORD} caracteres`,
  repetirVacio: "Escribí la contraseña otra vez",
  noCoinciden: "No coincide con la contraseña",
};

export const acceso = {
  // El nombre de la app, arriba de la tarjeta, lo pone la marca
  // (comp/Marca.tsx) con comun.marca.

  campos: {
    nombre: "Tu nombre",
    email: "Email",
    password: "Contraseña",
    repetirPassword: "Repetí la contraseña",
  },

  /** El botón que muestra lo que se escribió en un campo de contraseña. Se
   *  ve "Mostrar" u "Ocultar": es la acción, no el estado. El sufijo va oculto
   *  a la vista, justo después, y nombra el campo (en Crear cuenta hay dos).
   *  El nombre que lee el lector de pantalla empieza con la palabra visible,
   *  así quien maneja el celular por voz dice "tocar Mostrar" y lo encuentra.
   *  El espacio del principio es a propósito: separa las dos partes. */
  mostrarPassword: "Mostrar",
  ocultarPassword: "Ocultar",
  sufijoPasswordOculto: (campo: string) => ` lo que escribiste en ${campo}`,

  /** Oculto, antes de una ayuda que ya se cumple: lo que el tilde verde dice
   *  a la vista ("Listo: Coinciden"). */
  cumplido: "Listo:",

  entrar: {
    tituloPestana: "Entrar",
    subtitulo: "Panel para organizar tus eventos",
    boton: "Entrar",
    /** El botón mientras espera la respuesta, con el círculo que gira. */
    entrando: "Entrando…",
    /** Debajo del botón, si la respuesta tarda más de unos segundos: casi
     *  siempre, la app estaba dormida y se está despertando. */
    tarda: "Está tardando un poco más. Si hacía rato que nadie entraba, puede llevar hasta un minuto.",
    faltanDatos: "Escribí tu email y tu contraseña",
    sinCuenta: "¿No tenés cuenta?",
    crearCuenta: "Creá una",
    olvide: "¿Olvidaste tu contraseña?",
  },

  registro: {
    tituloPestana: "Crear cuenta",
    titulo: "Creá tu cuenta",
    subtitulo: "Para organizar tus propios eventos",
    boton: "Crear cuenta",
    conCuenta: "¿Ya tenés cuenta?",
    irAEntrar: "Entrá",

    ayudaPassword,
    coinciden: "Coinciden",

    errores: {
      nombreVacio: "Escribí tu nombre",
      nombreLargo: `Hasta ${MAXIMO_NOMBRE} caracteres`,
      ...erroresEmail,
      ...erroresPassword,
    },

    exito: {
      tituloPestana: "Cuenta pedida",
      titulo: "Listo",
      mensaje: "Cuando alguien que administra la app habilite tu cuenta, vas a poder entrar.",
      conEmail: (email: string) => `La pediste con ${email}.`,
      volver: "Volver a Entrar",
    },
  },

  /** /admin/olvide: pedir el link para elegir una contraseña nueva. La
   *  respuesta es la misma haya o no una cuenta con ese email, y la
   *  confirmación tampoco promete nada distinto. */
  olvide: {
    tituloPestana: "Olvidé mi contraseña",
    titulo: "¿Olvidaste tu contraseña?",
    subtitulo: "Escribí tu email y te mandamos un link para elegir una nueva.",
    boton: "Mandarme el link",
    volver: "Volver a Entrar",
    errores: erroresEmail,

    enviado: {
      tituloPestana: "Revisá tu email",
      titulo: "Revisá tu email",
      mensaje: "Si hay una cuenta con ese email, te mandamos un link.",
      noDeseado: "Revisá también el correo no deseado.",
      conEmail: (email: string) => `Lo pediste para ${email}.`,
      volver: "Volver a Entrar",
      escribisteMal: "¿Lo escribiste mal?",
      cambiar: "Cambialo",
    },
  },

  /** /admin/restablecer#token=…: el link del email. */
  restablecer: {
    tituloPestana: "Contraseña nueva",
    titulo: "Elegí una contraseña nueva",
    subtitulo: "Es la que vas a usar para entrar.",
    campos: {
      password: "Contraseña nueva",
      repetir: "Repetí la contraseña nueva",
    },
    boton: "Guardar contraseña",
    volver: "Volver a Entrar",
    ayudaPassword,
    coinciden: "Coinciden",
    errores: erroresPassword,

    listo: {
      tituloPestana: "Contraseña cambiada",
      titulo: "Listo",
      mensaje: "Ya podés entrar con tu contraseña nueva.",
      otrosLados: "Donde tenías el panel abierto, vas a tener que entrar de nuevo.",
      entrar: "Entrar",
    },

    /** Link vencido, usado, reemplazado por uno más nuevo, o sin token. Es el
     *  mismo mensaje que manda el backend (_LINK_VENCIDO en
     *  routers/cuentas.py): acá se usa sólo cuando al link le falta el token y
     *  no hay nada que preguntarle. Si el backend contesta, va su mensaje. */
    invalido: {
      tituloPestana: "El link ya no sirve",
      mensaje: "El link ya no sirve. Pedí uno nuevo.",
      porQue: "Cada link sirve una sola vez y vence en una hora. Si pediste varios, sirve el último.",
      pedirOtro: "Pedir otro link",
      volver: "Volver a Entrar",
    },
  },
} as const;

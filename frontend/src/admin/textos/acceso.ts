// Textos de las dos páginas de acceso: Entrar y Crear cuenta.
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

/** Lo mismo que exige el backend (PedidoRegistro en schemas.py). */
export const MINIMO_PASSWORD = 10;
export const MAXIMO_PASSWORD = 128;
export const MAXIMO_NOMBRE = 80;

export const acceso = {
  marca: "Transmití tu foto",

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
    faltanDatos: "Escribí tu email y tu contraseña",
    sinCuenta: "¿No tenés cuenta?",
    crearCuenta: "Creá una",
  },

  registro: {
    tituloPestana: "Crear cuenta",
    titulo: "Creá tu cuenta",
    subtitulo: "Para organizar tus propios eventos",
    boton: "Crear cuenta",
    conCuenta: "¿Ya tenés cuenta?",
    irAEntrar: "Entrá",

    ayudaPassword: (largo: number) => {
      if (largo === 0) return `Mínimo ${MINIMO_PASSWORD} caracteres`;
      if (largo < MINIMO_PASSWORD) {
        const faltan = MINIMO_PASSWORD - largo;
        return `Mínimo ${MINIMO_PASSWORD} caracteres · te ${faltan === 1 ? "falta 1" : `faltan ${faltan}`}`;
      }
      // Cumplida: el mismo texto, en verde y con el tilde que pone el campo.
      return `Mínimo ${MINIMO_PASSWORD} caracteres`;
    },
    coinciden: "Coinciden",

    errores: {
      nombreVacio: "Escribí tu nombre",
      nombreLargo: `Hasta ${MAXIMO_NOMBRE} caracteres`,
      emailVacio: "Escribí tu email",
      emailInvalido: "Ese email no está completo. Revisalo",
      passwordLarga: `Hasta ${MAXIMO_PASSWORD} caracteres`,
      repetirVacio: "Escribí la contraseña otra vez",
      noCoinciden: "No coincide con la contraseña",
    },

    exito: {
      tituloPestana: "Cuenta pedida",
      titulo: "Listo",
      mensaje: "Cuando alguien que administra la app habilite tu cuenta, vas a poder entrar.",
      conEmail: (email: string) => `La pediste con ${email}.`,
      volver: "Volver a Entrar",
    },
  },
} as const;

// Textos de la página Cuentas (la ven admins y superadmins). Los estados, los
// roles y los verbos compartidos viven en comun.ts.
//
// Las confirmaciones dicen qué cambia para la otra persona, no qué hace el
// sistema: "no va a poder entrar", no "se cambia el estado a baja".

/** Lo que un admin puede hacer con una cuenta ajena. */
export type AccionCuenta =
  | "habilitar"
  | "habilitarAdmin"
  | "rechazar"
  | "hacerAdmin"
  | "quitarAdmin"
  | "darBaja"
  | "reactivar";

/** Las que piden confirmación antes de mandarse. Habilitar y reactivar no:
 *  dan acceso, no lo quitan, y si fue un error se da de baja. */
export type AccionConfirmada = Exclude<AccionCuenta, "habilitar" | "reactivar">;

interface Confirmacion {
  titulo: (nombre: string) => string;
  mensaje: string;
  confirmar: string;
}

// Lo mismo se explica al habilitar como admin y al hacer admin: que sea igual.
// Un admin gestiona organizadores; a los admins, sólo una cuenta superadmin.
const PODERES_DE_ADMIN =
  "Va a ver y cambiar todos los eventos, y va a poder habilitar o dar de baja cuentas de organizador.";

export const textosCuentas = {
  titulo: "Cuentas",
  cargando: "Cargando cuentas…",

  pendientes: {
    titulo: "Esperando habilitación",
    explicacion:
      "Cada persona crea su cuenta sola y no puede entrar hasta que la habilites. Para invitar a alguien, pasale el link para crear cuenta.",
    vacio: "Nadie está esperando.",
    pidio: (fecha: string) => `Pidió la cuenta el ${fecha}`,
    copiarLink: "Copiar link para crear cuenta",
    /** Si el navegador no deja copiar, se muestra el link en un cuadro. */
    etiquetaLink: "Link para crear cuenta",
  },

  activas: {
    titulo: "Activas",
  },

  bajas: {
    titulo: "Dadas de baja",
  },

  vos: "Vos",
  // Por qué una tarjeta no tiene botones de rol ni de estado: lo mismo que
  // rechaza el backend, dicho sin palabras del sistema.
  /** La propia, mirada por un admin. */
  propia: "Tu rol y tu estado sólo los cambia una cuenta superadmin.",
  /** La propia, mirada por la superadmin. */
  propiaSuperadmin: "Nadie cambia tu rol ni tu estado desde el panel.",
  /** Una superadmin, mirada por cualquiera. */
  intocableSuperadmin: "A una cuenta superadmin no la cambia nadie desde el panel.",
  /** Otro admin, mirado por un admin. */
  soloSuperadmin: "A una cuenta admin sólo la cambia una cuenta superadmin.",

  eventos: (n: number) => (n === 1 ? "1 evento" : `${n} eventos`),
  ultimoEvento: (fecha: string) => `último: ${fecha}`,
  sinEventos: "Sin eventos",
  verHistorial: "Ver historial",

  acciones: {
    habilitar: "Habilitar",
    habilitarAdmin: "Habilitar como admin",
    rechazar: "Rechazar",
    hacerAdmin: "Hacer admin",
    quitarAdmin: "Quitar admin",
    darBaja: "Dar de baja",
    reactivar: "Reactivar",
  } satisfies Record<AccionCuenta, string>,

  confirmaciones: {
    habilitarAdmin: {
      titulo: (nombre) => `¿Habilitar a ${nombre} como admin?`,
      mensaje: PODERES_DE_ADMIN,
      confirmar: "Habilitar como admin",
    },
    rechazar: {
      titulo: (nombre) => `¿Rechazar a ${nombre}?`,
      mensaje: "No va a poder entrar. Si te equivocaste, la reactivás desde “Dadas de baja”.",
      confirmar: "Rechazar",
    },
    hacerAdmin: {
      titulo: (nombre) => `¿Hacer admin a ${nombre}?`,
      mensaje: PODERES_DE_ADMIN,
      confirmar: "Hacer admin",
    },
    quitarAdmin: {
      titulo: (nombre) => `¿Quitarle el rol de admin a ${nombre}?`,
      mensaje: "Va a seguir entrando, pero sólo va a ver sus propios eventos.",
      confirmar: "Quitar admin",
    },
    darBaja: {
      titulo: (nombre) => `¿Dar de baja a ${nombre}?`,
      mensaje:
        "No va a poder entrar. Sus eventos y fotos quedan y los seguís viendo. " +
        "Si hace falta, la reactivás desde “Dadas de baja”.",
      confirmar: "Dar de baja",
    },
  } satisfies Record<AccionConfirmada, Confirmacion>,

  /**
   * Eliminar definitivamente: la única excepción a "nada se borra". Sólo lo ve
   * una superadmin, y nunca sobre otra superadmin ni sobre la propia cuenta.
   * Se borran el nombre, el email y la contraseña; los eventos, con fotos y
   * videos, pasan a la cuenta de quien elimina. Se confirma escribiendo el
   * email de la cuenta.
   */
  eliminar: {
    accion: "Eliminar definitivamente",
    titulo: (nombre: string) => `¿Eliminar a ${nombre} para siempre?`,
    noSeDeshace: "No se puede deshacer.",
    seBorra: "Se borran su nombre, su email y su contraseña.",
    /** n = los eventos que tiene hoy: los que van a pasar a tu cuenta. */
    eventos: (n: number) =>
      n === 0
        ? "No tiene eventos."
        : n === 1
          ? "Su evento, con las fotos y los videos, pasa a tu cuenta."
          : `Sus ${n} eventos, con las fotos y los videos, pasan a tu cuenta.`,
    etiqueta: "Para confirmar, escribí su email:",
    confirmar: "Eliminar definitivamente",
    /** El aviso de abajo. n = los que pasaron de verdad, según el backend. */
    hecho: (n: number) =>
      n === 0
        ? "Cuenta eliminada."
        : n === 1
          ? "Cuenta eliminada. Su evento pasó a tu cuenta."
          : `Cuenta eliminada. Sus ${n} eventos pasaron a tu cuenta.`,
  },

  /** El aviso de abajo, después de cada cambio: la tarjeta suele mudarse de
   *  sección y sin esto parece que desapareció. */
  hecho: {
    habilitar: (nombre: string) => `${nombre} ya puede entrar.`,
    habilitarAdmin: (nombre: string) => `${nombre} ya puede entrar, como admin.`,
    rechazar: (nombre: string) => `Rechazaste a ${nombre}.`,
    hacerAdmin: (nombre: string) => `${nombre} ahora es admin.`,
    quitarAdmin: (nombre: string) => `${nombre} ya no es admin.`,
    darBaja: (nombre: string) => `Diste de baja a ${nombre}.`,
    reactivar: (nombre: string) => `${nombre} puede volver a entrar.`,
  } satisfies Record<AccionCuenta, (nombre: string) => string>,
} as const;

// Espejo del contrato de la sección 5 de CONSTRUIR-APP.md.
// Si acá y en backend/app/schemas.py dicen cosas distintas, manda el contrato.

export type EstadoEvento = "borrador" | "activo" | "cerrado";
export type EstadoFoto = "pendiente" | "aprobada" | "rechazada";

/** Los diez códigos del contrato. */
export type CodigoError =
  | "EVENTO_NO_ENCONTRADO"
  | "EVENTO_CERRADO"
  | "EVENTO_BORRADOR"
  | "FOTO_NO_ENCONTRADA"
  | "ARCHIVO_INVALIDO"
  | "PUBLIC_ID_AJENO"
  | "LIMITE_ALCANZADO"
  | "DEMASIADOS_PEDIDOS"
  | "NO_AUTORIZADO"
  | "DATOS_INVALIDOS";

export interface RespuestaError {
  error: { codigo: CodigoError; mensaje: string };
}

// ── Públicos: los usa el celular del invitado ────────────────

/** El id interno del evento no aparece acá. Regla 1. */
export interface EventoPublico {
  nombre: string;
  fecha_evento: string;
  estado: EstadoEvento;
  max_fotos_por_dispositivo: number;
}

export interface PedidoFirma {
  dispositivo_hash: string;
}

export interface Firma {
  cloud_name: string;
  api_key: string;
  timestamp: number;
  signature: string;
  folder: string;
}

export interface FotoNueva {
  public_id: string;
  url: string;
  ancho: number;
  alto: number;
  bytes: number;
  dispositivo_hash: string;
  nombre_invitado?: string | null;
}

export interface FotoRegistrada {
  id: number;
  estado: EstadoFoto;
}

// ── Pantalla ─────────────────────────────────────────────────

/** Cómo se ve la pantalla del evento. Lo elige quien organiza en Ajustes;
 *  un evento nuevo copia los predeterminados de su dueño (Mi cuenta). */
export type FondoPantalla = "desenfocado" | "negro";
export type TransicionPantalla = "fundido" | "corte";

export interface EstiloPantalla {
  /** Lo que llena el espacio que la foto no ocupa: la misma foto ampliada y
   *  desenfocada, o negro. */
  fondo: FondoPantalla;
  /** Entre una foto y la siguiente: fundido o corte seco. */
  transicion: TransicionPantalla;
  /** El nombre de quien la mandó, abajo, si lo escribió. */
  mostrar_nombre: boolean;
  /** El QR para mandar fotos, en una esquina. */
  mostrar_qr: boolean;
}

export interface Pantalla {
  evento: { nombre: string; codigo_publico: string; estado: EstadoEvento };
  /** La pantalla lo vuelve a pedir en cada pasada de polling: un cambio de
   *  estilo en Ajustes se ve sin recargar. */
  config: EstiloPantalla & {
    segundos_por_foto: number;
    intervalo_polling_ms: number;
    maximo_buffer: number;
  };
}

export interface FotoPantalla {
  id: number;
  url: string;
  ancho: number | null;
  alto: number | null;
  nombre_invitado: string | null;
}

export interface ColaPantalla {
  fotos: FotoPantalla[];
  ultimo_id: number;
}

// ── Administración ───────────────────────────────────────────

export interface PedidoLogin {
  email: string;
  password: string;
}

export interface Sesion {
  token: string;
  expira_en: string;
}

/** Cuerpo de PATCH /api/admin/eventos/{id}: cualquier combinación, al menos uno. */
export interface CambioEvento {
  estado?: EstadoEvento;
  segundos_por_foto?: number;
  max_fotos_por_dispositivo?: number;
  pantalla_fondo?: FondoPantalla;
  pantalla_transicion?: TransicionPantalla;
  pantalla_mostrar_nombre?: boolean;
  pantalla_mostrar_qr?: boolean;
}

export interface EventoNuevo {
  nombre: string;
  fecha_evento: string;
  /** Sólo un admin lo usa, para crearle el evento a otra cuenta activa. Sin
   *  esto, el dueño es quien lo crea. */
  organizador_id?: number;
}

export interface EventoAdmin {
  id: number;
  nombre: string;
  fecha_evento: string;
  estado: EstadoEvento;
  codigo_publico: string;
  token_pantalla: string;
  segundos_por_foto: number;
  max_fotos_por_dispositivo: number;
  pendientes: number;
  aprobadas: number;
  rechazadas: number;
  /** Dueño del evento. Un organizador sólo ve los suyos; un admin, todos. */
  organizador_id: number;
  organizador_nombre: string;
  /**
   * Fecha (YYYY-MM-DD) en que se borran de Cloudinary todas las fotos y todos
   * los videos del evento: fecha_evento + 30 días. Las filas de la base quedan.
   * Se borran en la primera pasada de limpieza con hoy (Argentina) >= esta fecha.
   */
  fotos_se_borran_el: string;
  /** Cuándo se borraron (ISO con zona), o null si todavía están. Con esto
   *  puesto el evento queda cerrado y no se ofrece ni descarga ni video. */
  fotos_borradas_en: string | null;
  /** La URL del último video si está listo y las fotos no se borraron; si no,
   *  null. Es lo que usa el botón "Descargar video". */
  video_url_listo: string | null;
  /** El estilo de la pantalla (ver EstiloPantalla). Al crear el evento se
   *  copian de los predeterminados del dueño. */
  pantalla_fondo: FondoPantalla;
  pantalla_transicion: TransicionPantalla;
  pantalla_mostrar_nombre: boolean;
  pantalla_mostrar_qr: boolean;
}

/** Query de GET /api/admin/eventos. Sin alcance vienen todos. Regla de
 *  medianoche (hoy = Argentina):
 *  vigentes = abiertos de cualquier fecha + sin publicar de hoy en adelante;
 *  historial = terminados + sin publicar de fecha pasada.
 *  admin/navegacion.ts (esDelHistorial) la replica. */
export type AlcanceEventos = "vigentes" | "historial";

export interface FiltroEventos {
  alcance?: AlcanceEventos;
  /** Sólo lo respeta el backend si quien pide es admin. */
  organizador?: number;
}

// ── Cuentas y roles ──────────────────────────────────────────
// Las cuentas se crean solas desde el registro público y nacen pendientes.
// Darlas de baja no borra nada: sus eventos y fotos quedan.

/** superadmin es la dueña de la app: todo lo de un admin y además gestiona a
 *  los admins. Nadie la nombra desde el panel. */
export type RolUsuario = "superadmin" | "admin" | "organizador";
export type EstadoCuenta = "pendiente" | "activa" | "baja";

/** El tema del panel que eligió la cuenta. Automático sigue al del sistema.
 *  El invitado y la pantalla son siempre oscuros, sin importar esto. */
export type Tema = "oscuro" | "claro" | "automatico";

/** Con qué arranca cada evento nuevo de la cuenta. Después, cada evento se
 *  cambia en sus Ajustes sin tocar esto. */
export interface Predeterminados {
  /** 3 a 30. */
  segundos_por_foto: number;
  /** 1 a 50. */
  max_fotos_por_dispositivo: number;
  pantalla: EstiloPantalla;
}

/** GET /api/admin/yo, y la respuesta de todo lo de /api/admin/yo que cambia
 *  algo (PATCH, avatar). */
export interface UsuarioYo {
  id: number;
  email: string;
  nombre: string;
  rol: RolUsuario;
  /** La foto de la cuenta (Cloudinary), o null. */
  avatar_url: string | null;
  tema: Tema;
  predeterminados: Predeterminados;
}

/** Cuerpo de PATCH /api/admin/yo: al menos uno. Los predeterminados pueden ir
 *  por partes (sólo lo que cambió). No cambia email, rol ni estado. */
export interface CambioYo {
  nombre?: string;
  tema?: Tema;
  predeterminados?: Partial<Omit<Predeterminados, "pantalla">> & {
    pantalla?: Partial<EstiloPantalla>;
  };
}

/** Cuerpo de POST /api/admin/yo/contrasena. `nueva`: 10 a 128 caracteres.
 *  Responde una Sesion nueva: las demás sesiones de la cuenta dejan de servir,
 *  la de quien la cambió sigue con el token nuevo. */
export interface PedidoCambioContrasena {
  actual: string;
  nueva: string;
}

/** Cuerpo de PUT /api/admin/yo/avatar, después de subir la imagen a
 *  Cloudinary con la firma de POST /api/admin/yo/avatar/firma. El backend
 *  verifica que `public_id` esté en avatares/{id de la cuenta}/ y que `url` sea
 *  de la cuenta de Cloudinary de la app (si no, PUBLIC_ID_AJENO o
 *  ARCHIVO_INVALIDO). */
export interface AvatarNuevo {
  public_id: string;
  url: string;
}

/** GET /api/admin/cuentas (sólo admin) y respuesta de PATCH /api/admin/cuentas/{id} */
export interface Cuenta {
  id: number;
  email: string;
  nombre: string;
  rol: RolUsuario;
  estado: EstadoCuenta;
  creado_en: string;
  /** Cuántos eventos tiene. */
  eventos: number;
  /** fecha_evento más reciente, o null si no tiene ninguno. */
  ultimo_evento: string | null;
  /** La foto de la cuenta, o null. */
  avatar_url: string | null;
}

/** Cuerpo de PATCH /api/admin/cuentas/{id}: al menos uno. 'pendiente' no se
 *  acepta: una cuenta habilitada no vuelve a esperar. 'superadmin' tampoco: no
 *  se asigna desde el panel. Nadie cambia su propio rol ni su propio estado. */
export interface CambioCuenta {
  estado?: Exclude<EstadoCuenta, "pendiente">;
  rol?: Exclude<RolUsuario, "superadmin">;
  nombre?: string;
}

/** Cuerpo de DELETE /api/admin/cuentas/{id}: la única excepción a "nada se
 *  borra", y sólo para una superadmin. El email va en el cuerpo y no en la
 *  URL; tiene que coincidir con el de la cuenta (sin distinguir mayúsculas ni
 *  espacios alrededor) o el backend responde 422 y no borra nada. Ni una
 *  superadmin ni la propia cuenta se eliminan. */
export interface PedidoEliminarCuenta {
  confirmar_email: string;
}

/** Respuesta de DELETE /api/admin/cuentas/{id}. Se borra sólo la fila de la
 *  cuenta (nombre, email y contraseña); sus eventos, con fotos y videos, pasan
 *  a la superadmin que la eliminó. Esto dice cuántos pasaron. */
export interface CuentaEliminada {
  eventos_transferidos: number;
}

/** POST /api/cuentas/registro (público) */
export interface PedidoRegistro {
  email: string;
  nombre: string;
  password: string;
}

/** Siempre la misma respuesta, exista o no el email: así no se puede averiguar
 *  qué emails están registrados. */
export interface RespuestaRegistro {
  estado: "pendiente";
}

/** POST /api/cuentas/recuperar (público). Siempre la misma respuesta, exista
 *  o no la cuenta: no se puede averiguar qué emails están registrados. Si
 *  existe y está activa, le llega un email con un link que vence en una hora. */
export interface PedidoRecuperar {
  email: string;
}

export interface RespuestaRecuperar {
  enviado: true;
}

/** POST /api/cuentas/restablecer (público). `token` sale del link del email
 *  (/admin/restablecer#token=…). Si no sirve (vencido, usado, de una cuenta
 *  que ya no está activa) responde 422 con un solo mensaje para todos los
 *  casos. Si sirve, cierra todas las sesiones abiertas de esa cuenta. */
export interface PedidoRestablecer {
  token: string;
  password: string;
}

export interface RespuestaRestablecer {
  restablecida: true;
}

/** GET y POST /api/admin/eventos/{id}/video */
export interface VideoEvento {
  estado: "ninguno" | "procesando" | "listo" | "fallo";
  url: string | null;
  fotos: number | null;
  pedido_en: string | null;
}

export interface FotoAdmin {
  id: number;
  url: string;
  ancho: number | null;
  alto: number | null;
  bytes: number | null;
  estado: EstadoFoto;
  nombre_invitado: string | null;
  subida_en: string;
}

export interface ListaFotosAdmin {
  fotos: FotoAdmin[];
  ultimo_id: number;
}

export interface Resumen {
  pendientes: number;
  aprobadas: number;
  rechazadas: number;
}

export interface FotoModerada {
  id: number;
  estado: EstadoFoto;
}

export interface LoteModeracion {
  ids: number[];
  estado: EstadoFoto;
}

export interface ResultadoLote {
  afectadas: number;
}

// ── Vinculación de pantalla por código corto ─────────────────
// Agregado fuera del contrato de la sección 5, propuesto y aprobado antes de
// escribirlo: el link de la pantalla mide 68 caracteres y hay que poder
// cargarlo con el control remoto de una tele.

export interface CodigoVinculacion {
  codigo: string;
  expira_en: string;
}

export interface TokenDePantalla {
  token_pantalla: string;
}

export interface Salud {
  estado: string;
  base: string;
}

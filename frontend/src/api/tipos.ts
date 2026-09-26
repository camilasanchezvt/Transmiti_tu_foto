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

export interface Pantalla {
  evento: { nombre: string; codigo_publico: string; estado: EstadoEvento };
  config: {
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

/** GET /api/admin/yo */
export interface UsuarioYo {
  id: number;
  email: string;
  nombre: string;
  rol: RolUsuario;
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
}

/** Cuerpo de PATCH /api/admin/cuentas/{id}: al menos uno. 'pendiente' no se
 *  acepta: una cuenta habilitada no vuelve a esperar. 'superadmin' tampoco: no
 *  se asigna desde el panel. Nadie cambia su propio rol ni su propio estado. */
export interface CambioCuenta {
  estado?: Exclude<EstadoCuenta, "pendiente">;
  rol?: Exclude<RolUsuario, "superadmin">;
  nombre?: string;
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

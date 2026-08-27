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

export interface EventoNuevo {
  nombre: string;
  fecha_evento: string;
}

export interface EventoAdmin {
  id: number;
  nombre: string;
  fecha_evento: string;
  estado: EstadoEvento;
  codigo_publico: string;
  token_pantalla: string;
  pendientes: number;
  aprobadas: number;
  rechazadas: number;
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

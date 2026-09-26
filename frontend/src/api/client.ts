// Cliente HTTP contra FastAPI.
//
// Ninguna pantalla habla con Supabase directamente: todo pasa por acá (regla 3).
// Todos los errores del backend tienen la misma forma, así que se traducen a un
// solo tipo de excepción y las pantallas nunca leen `response.json()` a mano.

import type {
  CambioCuenta,
  ColaPantalla,
  CodigoError,
  CodigoVinculacion,
  Cuenta,
  CuentaEliminada,
  EventoAdmin,
  CambioEvento,
  EventoNuevo,
  EventoPublico,
  EstadoEvento,
  EstadoFoto,
  FiltroEventos,
  Firma,
  FotoModerada,
  FotoNueva,
  FotoRegistrada,
  ListaFotosAdmin,
  Pantalla,
  PedidoEliminarCuenta,
  PedidoLogin,
  PedidoRegistro,
  RespuestaRegistro,
  ResultadoLote,
  Resumen,
  Salud,
  Sesion,
  UsuarioYo,
  VideoEvento,
  TokenDePantalla,
} from "./tipos";
import { textosBase } from "../comp/textos";

const BASE = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

/** Un error que el backend describió con un código del contrato. */
export class ErrorApi extends Error {
  readonly codigo: CodigoError | "SIN_RED";
  readonly http: number;

  constructor(codigo: CodigoError | "SIN_RED", mensaje: string, http: number) {
    super(mensaje);
    this.name = "ErrorApi";
    this.codigo = codigo;
    this.http = http;
  }

  /** Cuando no hubo respuesta: el celular perdió señal o el servidor duerme. */
  get esDeRed(): boolean {
    return this.codigo === "SIN_RED";
  }

  /** 401: no hay sesión, venció, o la cuenta se dio de baja. Hay que volver a
   *  entrar. Ojo: NO_AUTORIZADO también viaja con 403, así que el código solo
   *  no alcanza para decidir si mandar al login. */
  get esSinSesion(): boolean {
    return this.http === 401;
  }

  /** 403: hay sesión pero no alcanza el permiso (una pantalla de admin pedida
   *  por un organizador, o en el login una cuenta pendiente o de baja). */
  get esSinPermiso(): boolean {
    return this.http === 403;
  }

  /** 410: las fotos y el video del evento ya se borraron de Cloudinary (a los
   *  30 días de la fecha). Lo responden la descarga y el video; el mensaje del
   *  backend ya lo dice, pero así la página puede dejar de ofrecerlos. */
  get esFotosBorradas(): boolean {
    return this.http === 410;
  }
}

let tokenAdmin: string | null = leerTokenGuardado();

function leerTokenGuardado(): string | null {
  try {
    return window.localStorage.getItem("transmiti.token");
  } catch {
    // Modo privado en iOS: localStorage tira. No es motivo para no andar.
    return null;
  }
}

export function guardarToken(token: string | null): void {
  tokenAdmin = token;
  try {
    if (token) window.localStorage.setItem("transmiti.token", token);
    else window.localStorage.removeItem("transmiti.token");
  } catch {
    /* la sesión vive sólo en memoria */
  }
}

export function haySesion(): boolean {
  return tokenAdmin !== null;
}

/** El token actual. Lo usa useSesion para saber si lo que tiene en memoria es
 *  de esta sesión o de una anterior (entrar con otra cuenta cambia el token). */
export function tokenDeSesion(): string | null {
  return tokenAdmin;
}

interface Opciones {
  metodo?: "GET" | "POST" | "PATCH" | "DELETE";
  cuerpo?: unknown;
  conAuth?: boolean;
  senal?: AbortSignal;
}

async function pedir<T>(ruta: string, opciones: Opciones = {}): Promise<T> {
  const { metodo = "GET", cuerpo, conAuth = false, senal } = opciones;

  const cabeceras: Record<string, string> = {};
  if (cuerpo !== undefined) cabeceras["Content-Type"] = "application/json";
  if (conAuth && tokenAdmin) cabeceras["Authorization"] = `Bearer ${tokenAdmin}`;

  let respuesta: Response;
  try {
    respuesta = await fetch(`${BASE}${ruta}`, {
      method: metodo,
      headers: cabeceras,
      body: cuerpo === undefined ? undefined : JSON.stringify(cuerpo),
      signal: senal,
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") throw error;
    // Render gratuito duerme el servicio: el primer pedido puede tardar cerca
    // de un minuto o directamente fallar.
    throw new ErrorApi("SIN_RED", textosBase.sinRed, 0);
  }

  if (respuesta.status === 204) return undefined as T;

  if (!respuesta.ok) {
    throw await comoErrorApi(respuesta);
  }

  return (await respuesta.json()) as T;
}

async function comoErrorApi(respuesta: Response): Promise<ErrorApi> {
  // El backend siempre manda { error: { codigo, mensaje } }. Pero un 502 de un
  // proxy, o Render devolviendo su propia página mientras despierta, no lo
  // respeta: por eso se contempla que el cuerpo no sea el esperado.
  try {
    const cuerpo = (await respuesta.json()) as { error?: { codigo?: string; mensaje?: string } };
    const codigo = cuerpo?.error?.codigo;
    const mensaje = cuerpo?.error?.mensaje;
    if (codigo && mensaje) {
      return new ErrorApi(codigo as CodigoError, mensaje, respuesta.status);
    }
  } catch {
    /* el cuerpo no era JSON */
  }
  return new ErrorApi("SIN_RED", textosBase.errorGenerico, respuesta.status);
}

// ── Públicos ─────────────────────────────────────────────────

export const publico = {
  evento: (codigo: string) => pedir<EventoPublico>(`/api/e/${encodeURIComponent(codigo)}`),

  firma: (codigo: string, dispositivo_hash: string) =>
    pedir<Firma>(`/api/e/${encodeURIComponent(codigo)}/firma`, {
      metodo: "POST",
      cuerpo: { dispositivo_hash },
    }),

  registrarFoto: (codigo: string, foto: FotoNueva) =>
    pedir<FotoRegistrada>(`/api/e/${encodeURIComponent(codigo)}/fotos`, {
      metodo: "POST",
      cuerpo: foto,
    }),
};

// ── Pantalla ─────────────────────────────────────────────────

const CLAVE_PANTALLA = "transmiti.pantalla";

export const pantalla = {
  /** Canjea el código de seis dígitos por el token. Es lo que evita tipear 68
   *  caracteres con el control remoto de una tele. */
  canjear: async (codigo: string) => {
    const respuesta = await pedir<TokenDePantalla>("/api/pantalla/canjear", {
      metodo: "POST",
      cuerpo: { codigo },
    });
    guardarPantalla(respuesta.token_pantalla);
    return respuesta.token_pantalla;
  },

  config: (token: string, senal?: AbortSignal) =>
    pedir<Pantalla>(`/api/pantalla/${encodeURIComponent(token)}`, { senal }),

  fotos: (token: string, desde: number, limite?: number, senal?: AbortSignal) => {
    const query = new URLSearchParams({ desde: String(desde) });
    if (limite !== undefined) query.set("limite", String(limite));
    return pedir<ColaPantalla>(
      `/api/pantalla/${encodeURIComponent(token)}/fotos?${query}`,
      { senal },
    );
  },
};

// ── Administración ───────────────────────────────────────────

/** El token vinculado queda guardado: la tele no lo vuelve a pedir al reiniciar. */
export function guardarPantalla(token: string | null): void {
  try {
    if (token) window.localStorage.setItem(CLAVE_PANTALLA, token);
    else window.localStorage.removeItem(CLAVE_PANTALLA);
  } catch {
    /* si el navegador de la tele no deja guardar, se vincula de nuevo */
  }
}

export function pantallaGuardada(): string | null {
  try {
    return window.localStorage.getItem(CLAVE_PANTALLA);
  } catch {
    return null;
  }
}

export const admin = {
  login: async (credenciales: PedidoLogin) => {
    const sesion = await pedir<Sesion>("/api/admin/login", {
      metodo: "POST",
      cuerpo: credenciales,
    });
    guardarToken(sesion.token);
    return sesion;
  },

  salir: () => guardarToken(null),

  /** Quién está usando el panel y con qué rol. */
  yo: () => pedir<UsuarioYo>("/api/admin/yo", { conAuth: true }),

  /** Todas las cuentas con su historial. Sólo admin: un organizador recibe 403. */
  cuentas: () => pedir<Cuenta[]>("/api/admin/cuentas", { conAuth: true }),

  /** Habilitar, dar de baja, reactivar, cambiar el rol o el nombre. Idempotente. */
  cambiarCuenta: (id: number, cambio: CambioCuenta) =>
    pedir<Cuenta>(`/api/admin/cuentas/${id}`, {
      metodo: "PATCH",
      cuerpo: cambio,
      conAuth: true,
    }),

  /** Borra la cuenta para siempre (nombre, email y contraseña). Sólo una
   *  superadmin; sus eventos, con fotos y videos, pasan a quien la elimina.
   *  `confirmar_email` tiene que ser el email de la cuenta: va en el cuerpo,
   *  nunca en la URL. */
  eliminarCuenta: (id: number, confirmar_email: string) =>
    pedir<CuentaEliminada>(`/api/admin/cuentas/${id}`, {
      metodo: "DELETE",
      cuerpo: { confirmar_email } satisfies PedidoEliminarCuenta,
      conAuth: true,
    }),

  /** Un admin ve todos; un organizador, sólo los suyos. Sin alcance vienen
   *  todos; `vigentes` llega por fecha ascendente e `historial` descendente. */
  eventos: (filtro: FiltroEventos = {}) => {
    const query = new URLSearchParams();
    if (filtro.alcance) query.set("alcance", filtro.alcance);
    if (filtro.organizador !== undefined) query.set("organizador", String(filtro.organizador));
    const cola = query.toString();
    return pedir<EventoAdmin[]>(`/api/admin/eventos${cola ? `?${cola}` : ""}`, { conAuth: true });
  },

  /** `organizador_id` es opcional: sólo un admin puede crearle un evento a otra cuenta. */
  crearEvento: (evento: EventoNuevo) =>
    pedir<EventoAdmin>("/api/admin/eventos", {
      metodo: "POST",
      cuerpo: evento,
      conAuth: true,
    }),

  cambiarEstadoEvento: (id: number, estado: EstadoEvento) =>
    pedir<EventoAdmin>(`/api/admin/eventos/${id}`, {
      metodo: "PATCH",
      cuerpo: { estado },
      conAuth: true,
    }),

  /** GET y POST del video. Con las fotos ya borradas responden 410
   *  (ErrorApi.esFotosBorradas). */
  video: (id: number) =>
    pedir<VideoEvento>(`/api/admin/eventos/${id}/video`, { conAuth: true }),

  armarVideo: (id: number) =>
    pedir<VideoEvento>(`/api/admin/eventos/${id}/video`, { metodo: "POST", conAuth: true }),

  configurarEvento: (id: number, cambio: CambioEvento) =>
    pedir<EventoAdmin>(`/api/admin/eventos/${id}`, {
      metodo: "PATCH",
      cuerpo: cambio,
      conAuth: true,
    }),

  fotos: (
    id: number,
    opciones: { estado?: EstadoFoto; desde?: number; limite?: number } = {},
  ) => {
    const query = new URLSearchParams();
    if (opciones.estado) query.set("estado", opciones.estado);
    if (opciones.desde !== undefined) query.set("desde", String(opciones.desde));
    if (opciones.limite !== undefined) query.set("limite", String(opciones.limite));
    const cola = query.toString();
    return pedir<ListaFotosAdmin>(
      `/api/admin/eventos/${id}/fotos${cola ? `?${cola}` : ""}`,
      { conAuth: true },
    );
  },

  vincularPantalla: (id: number) =>
    pedir<CodigoVinculacion>(`/api/admin/eventos/${id}/vincular`, {
      metodo: "POST",
      conAuth: true,
    }),

  resumen: (id: number) =>
    pedir<Resumen>(`/api/admin/eventos/${id}/resumen`, { conAuth: true }),

  moderar: (idFoto: number, estado: EstadoFoto) =>
    pedir<FotoModerada>(`/api/admin/fotos/${idFoto}`, {
      metodo: "PATCH",
      cuerpo: { estado },
      conAuth: true,
    }),

  moderarLote: (ids: number[], estado: EstadoFoto) =>
    pedir<ResultadoLote>("/api/admin/fotos/lote", {
      metodo: "POST",
      cuerpo: { ids, estado },
      conAuth: true,
    }),

  /** La descarga no pasa por `pedir`: es un ZIP, no JSON, y puede tardar.
   *  Con las fotos ya borradas responde 410 (ErrorApi.esFotosBorradas). */
  urlDescarga: (id: number, incluir: "aprobadas" | "todas") =>
    `${BASE}/api/admin/eventos/${id}/descarga?incluir=${incluir}`,

  descargar: async (id: number, incluir: "aprobadas" | "todas") => {
    const respuesta = await fetch(admin.urlDescarga(id, incluir), {
      headers: tokenAdmin ? { Authorization: `Bearer ${tokenAdmin}` } : {},
    });
    if (!respuesta.ok) throw await comoErrorApi(respuesta);
    return respuesta.blob();
  },
};

// ── Cuentas (público, sin token) ─────────────────────────────

export const cuentas = {
  /** Crea la cuenta pendiente. Responde lo mismo aunque el email ya exista:
   *  no hay forma de saber desde acá si ya estaba registrado. */
  registrar: (pedido: PedidoRegistro) =>
    pedir<RespuestaRegistro>("/api/cuentas/registro", {
      metodo: "POST",
      cuerpo: pedido,
    }),
};

export const salud = () => pedir<Salud>("/api/salud");

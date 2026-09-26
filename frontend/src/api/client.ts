// Cliente HTTP contra FastAPI.
//
// Ninguna pantalla habla con Supabase directamente: todo pasa por acá (regla 3).
// Todos los errores del backend tienen la misma forma, así que se traducen a un
// solo tipo de excepción y las pantallas nunca leen `response.json()` a mano.

import type {
  ColaPantalla,
  CodigoError,
  CodigoVinculacion,
  EventoAdmin,
  CambioEvento,
  EventoNuevo,
  EventoPublico,
  EstadoEvento,
  EstadoFoto,
  Firma,
  FotoModerada,
  FotoNueva,
  FotoRegistrada,
  ListaFotosAdmin,
  Pantalla,
  PedidoLogin,
  ResultadoLote,
  Resumen,
  Salud,
  Sesion,
  VideoEvento,
  TokenDePantalla,
} from "./tipos";

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

interface Opciones {
  metodo?: "GET" | "POST" | "PATCH";
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
    throw new ErrorApi("SIN_RED", "No pudimos conectarnos. Probá de nuevo", 0);
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
  return new ErrorApi("SIN_RED", "Algo salió mal. Probá de nuevo", respuesta.status);
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

  eventos: () => pedir<EventoAdmin[]>("/api/admin/eventos", { conAuth: true }),

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

  /** La descarga no pasa por `pedir`: es un ZIP, no JSON, y puede tardar. */
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

export const salud = () => pedir<Salud>("/api/salud");

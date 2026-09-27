// Cliente HTTP contra FastAPI.
//
// Ninguna pantalla habla con Supabase directamente: todo pasa por acá (regla 3).
// Todos los errores del backend tienen la misma forma, así que se traducen a un
// solo tipo de excepción y las pantallas nunca leen `response.json()` a mano.

import type {
  AvatarNuevo,
  CambioCuenta,
  CambioYo,
  ColaPantalla,
  CodigoError,
  CodigoVinculacion,
  Cuenta,
  CuentaEliminada,
  EventoAdmin,
  EventoBorrado,
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
  PedidoBorrarEvento,
  PedidoEliminarCuenta,
  PedidoCambioContrasena,
  PedidoLogin,
  PedidoRecuperar,
  PedidoRegistro,
  PedidoRestablecer,
  RespuestaRecuperar,
  RespuestaRegistro,
  RespuestaRestablecer,
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

// ── La sesión del panel ──────────────────────────────────────
//
// El token vive en memoria (tokenAdmin) y tiene una copia en localStorage,
// compartida por todas las pestañas del navegador. Con dos pestañas abiertas,
// la copia puede ser más nueva que lo que tiene en memoria una de ellas: al
// cambiar la contraseña, la pestaña A guarda un token nuevo y el de la pestaña
// B deja de servir. Tres reglas evitan que B, con su 401, le borre a A la
// sesión que acaba de renovar:
//
// 1. B toma el token guardado apenas cambia (evento `storage`).
// 2. Si igual le llega un 401 con el viejo, lo toma ahí y repite el pedido.
// 3. Olvidar la sesión borra la copia sólo si es la de esta pestaña.
//
// Efecto buscado: el navegador tiene UNA sesión, la última guardada. Si en
// otra pestaña se entra con otra cuenta, ésta pasa a esa cuenta también (igual
// que al recargar). No abre ningún acceso nuevo: los dos tokens ya estaban en
// este navegador. useSesion vuelve a preguntar quién es (alAdoptarToken), así
// el nombre, el rol y el tema que se muestran son los de la cuenta nueva.

const CLAVE_TOKEN = "transmiti.token";

let tokenAdmin: string | null = leerTokenGuardado();

/** La copia guardada del token, la que comparten todas las pestañas. */
export function leerTokenGuardado(): string | null {
  try {
    return window.localStorage.getItem(CLAVE_TOKEN);
  } catch {
    // Modo privado en iOS: localStorage tira. No es motivo para no andar.
    return null;
  }
}

export function guardarToken(token: string | null): void {
  const anterior = tokenAdmin;
  tokenAdmin = token;
  try {
    if (token) window.localStorage.setItem(CLAVE_TOKEN, token);
    // Salir, o una sesión que murió: se borra la copia sólo si todavía es la
    // de esta pestaña. Si otra ya guardó una más nueva, ésa queda.
    else if (leerTokenGuardado() === anterior) window.localStorage.removeItem(CLAVE_TOKEN);
  } catch {
    /* la sesión vive sólo en memoria */
  }
}

type AlAdoptar = (anterior: string, nuevo: string) => void;
const alAdoptar = new Set<AlAdoptar>();

/**
 * Para quien recuerda algo atado al token (useSesion): avisa cuando esta
 * pestaña tomó el token que guardó otra. Puede ser de otra cuenta, así que
 * hay que volver a preguntar quién es. Devuelve cómo desuscribirse.
 */
export function alAdoptarToken(avisar: AlAdoptar): () => void {
  alAdoptar.add(avisar);
  return () => {
    alAdoptar.delete(avisar);
  };
}

/**
 * Si otra pestaña guardó un token distinto del de ésta, lo toma: sólo cambia
 * la memoria, no navega. Una pestaña sin sesión (tocó Salir, o todavía no
 * entró) no toma nada: si alguien salió acá, sigue afuera. Devuelve si tomó.
 */
function adoptarTokenGuardado(): boolean {
  const anterior = tokenAdmin;
  const guardado = leerTokenGuardado();
  if (anterior === null || guardado === null || guardado === anterior) return false;
  tokenAdmin = guardado;
  alAdoptar.forEach((avisar) => avisar(anterior, guardado));
  return true;
}

if (typeof window !== "undefined") {
  // Sólo llega de OTRAS pestañas: la que guarda no recibe su propio evento.
  // Un borrado (newValue null) no se sigue: el Salir de otra pestaña no saca
  // a ésta, como siempre.
  window.addEventListener("storage", (evento) => {
    if (evento.key === CLAVE_TOKEN && evento.newValue) adoptarTokenGuardado();
  });
}

/** Con qué token salió el pedido que terminó en este error. Aparte y no en el
 *  error, para que el token no aparezca si alguien lo muestra en la consola. */
const tokenDelPedido = new WeakMap<ErrorApi, string>();

/**
 * Ante un 401: ¿esta pestaña se quedó sin sesión? No, si el pedido salió con
 * un token que ya no es el suyo, o si otra pestaña guardó uno nuevo (cambió la
 * contraseña, o volvió a entrar): en los dos casos sigue, con ése. Sólo si el
 * 401 fue con el token que tiene ahora, la sesión murió de verdad.
 */
export function perdioLaSesion(error: ErrorApi): boolean {
  if (!error.esSinSesion) return false;
  const usado = tokenDelPedido.get(error) ?? tokenAdmin;
  adoptarTokenGuardado();
  return tokenAdmin === null || tokenAdmin === usado;
}

/** ¿Se puede repetir un pedido que dio 401 con `usado`? Sí, si la pestaña ya
 *  tiene otro token: lo tomó de otra pestaña antes, o lo toma ahora. */
function hayOtroToken(usado: string | null): boolean {
  if (usado === null) return false;
  adoptarTokenGuardado();
  return tokenAdmin !== null && tokenAdmin !== usado;
}

type AlRenovar = (anterior: string | null, nuevo: string) => void;
const alRenovar = new Set<AlRenovar>();

/**
 * Para quien recuerda algo atado al token (useSesion): avisa cuando el token
 * cambia pero la cuenta es la MISMA, como al cambiar la contraseña. Así no se
 * vuelve a preguntar quién es ni parpadea el panel. Devuelve cómo desuscribirse.
 */
export function alRenovarToken(avisar: AlRenovar): () => void {
  alRenovar.add(avisar);
  return () => {
    alRenovar.delete(avisar);
  };
}

function renovarToken(nuevo: string): void {
  const anterior = tokenAdmin;
  guardarToken(nuevo);
  alRenovar.forEach((avisar) => avisar(anterior, nuevo));
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
  metodo?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  cuerpo?: unknown;
  conAuth?: boolean;
  senal?: AbortSignal;
}

async function pedir<T>(ruta: string, opciones: Opciones = {}): Promise<T> {
  const usado = opciones.conAuth ? tokenAdmin : null;
  try {
    return await pedirCon<T>(ruta, opciones, usado);
  } catch (error) {
    // Un 401 con un token viejo, cuando otra pestaña ya guardó uno nuevo: se
    // repite una sola vez con ése. El backend responde 401 antes de cambiar
    // nada, así que repetir no duplica ningún cambio.
    if (error instanceof ErrorApi && error.esSinSesion && hayOtroToken(usado)) {
      return pedirCon<T>(ruta, opciones, tokenAdmin);
    }
    throw error;
  }
}

async function pedirCon<T>(ruta: string, opciones: Opciones, token: string | null): Promise<T> {
  const { metodo = "GET", cuerpo, senal } = opciones;

  const cabeceras: Record<string, string> = {};
  if (cuerpo !== undefined) cabeceras["Content-Type"] = "application/json";
  if (token) cabeceras["Authorization"] = `Bearer ${token}`;

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
    throw await comoErrorApi(respuesta, token);
  }

  return (await respuesta.json()) as T;
}

/** `token`: con cuál salió el pedido, para perdioLaSesion. */
async function comoErrorApi(respuesta: Response, token: string | null): Promise<ErrorApi> {
  const error = await leerError(respuesta);
  if (token) tokenDelPedido.set(error, token);
  return error;
}

async function leerError(respuesta: Response): Promise<ErrorApi> {
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

  /** Quién está usando el panel: rol, avatar, tema y predeterminados. */
  yo: () => pedir<UsuarioYo>("/api/admin/yo", { conAuth: true }),

  /** Mi cuenta: nombre, tema y predeterminados (por partes). Devuelve la
   *  cuenta entera, como yo(). Para que el panel lo refleje al instante,
   *  pasale la respuesta a actualizarUsuarioEnSesion (useSesion). */
  actualizarYo: (cambio: CambioYo) =>
    pedir<UsuarioYo>("/api/admin/yo", { metodo: "PATCH", cuerpo: cambio, conAuth: true }),

  /** Cambia la contraseña. El backend cierra todas las sesiones de la cuenta
   *  y devuelve una nueva para esta: el token nuevo queda guardado acá, así
   *  quien la cambió sigue adentro. Con `actual` incorrecta, 422 con el
   *  mensaje para mostrar; con muchos intentos, 429. */
  cambiarContrasena: async (actual: string, nueva: string) => {
    const sesion = await pedir<Sesion>("/api/admin/yo/contrasena", {
      metodo: "POST",
      cuerpo: { actual, nueva } satisfies PedidoCambioContrasena,
      conAuth: true,
    });
    renovarToken(sesion.token);
    return sesion;
  },

  /** Firma para subir la foto de la cuenta directo a Cloudinary, a la carpeta
   *  avatares/{id}. La misma forma que la firma de las fotos del invitado:
   *  sirve con lib/subir.ts. */
  firmaAvatar: () =>
    pedir<Firma>("/api/admin/yo/avatar/firma", { metodo: "POST", conAuth: true }),

  /** Después de subirla: registra la foto de la cuenta. Devuelve la cuenta. */
  guardarAvatar: (public_id: string, url: string) =>
    pedir<UsuarioYo>("/api/admin/yo/avatar", {
      metodo: "PUT",
      cuerpo: { public_id, url } satisfies AvatarNuevo,
      conAuth: true,
    }),

  /** Saca la foto de la cuenta. Devuelve la cuenta. */
  quitarAvatar: () =>
    pedir<UsuarioYo>("/api/admin/yo/avatar/quitar", { metodo: "POST", conAuth: true }),

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

  /** Borra el evento para siempre, con sus fotos y su video. Sólo admin y
   *  superadmin, y sólo uno del Historial. `confirmar_nombre` tiene que ser el
   *  nombre del evento: va en el cuerpo, nunca en la URL. Si Cloudinary falla
   *  responde 503 y no borra nada. */
  borrarEvento: (id: number, confirmar_nombre: string) =>
    pedir<EventoBorrado>(`/api/admin/eventos/${id}`, {
      metodo: "DELETE",
      cuerpo: { confirmar_nombre } satisfies PedidoBorrarEvento,
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
    const bajar = (token: string | null) =>
      fetch(admin.urlDescarga(id, incluir), {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
    let usado = tokenAdmin;
    let respuesta = await bajar(usado);
    // Lo mismo que `pedir`: con el token viejo y uno nuevo de otra pestaña, se
    // repite una vez con ése.
    if (respuesta.status === 401 && hayOtroToken(usado)) {
      usado = tokenAdmin;
      respuesta = await bajar(usado);
    }
    if (!respuesta.ok) throw await comoErrorApi(respuesta, usado);
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

  /** "Olvidé mi contraseña". Responde lo mismo exista o no la cuenta; si
   *  existe, le llega un email con el link. Con muchos pedidos, 429. */
  recuperar: (email: string) =>
    pedir<RespuestaRecuperar>("/api/cuentas/recuperar", {
      metodo: "POST",
      cuerpo: { email } satisfies PedidoRecuperar,
    }),

  /** Elige la contraseña nueva con el token del link del email. No abre
   *  sesión: después, a Entrar. Si el link ya no sirve, 422 con un solo
   *  mensaje para todos los casos. */
  restablecer: (token: string, password: string) =>
    pedir<RespuestaRestablecer>("/api/cuentas/restablecer", {
      metodo: "POST",
      cuerpo: { token, password } satisfies PedidoRestablecer,
    }),
};

export const salud = () => pedir<Salud>("/api/salud");

import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import {
  ErrorApi,
  admin,
  alAdoptarToken,
  alRenovarToken,
  perdioLaSesion,
  tokenDeSesion,
} from "../api/client";
import type { UsuarioYo } from "../api/tipos";
import { aplicarTema } from "../lib/tema";

/**
 * Quién está usando el panel, pedido UNA vez por sesión.
 *
 * Cada página del panel lo necesita (la barra muestra el nombre, Cuentas sólo
 * aparece para un admin, Eventos muestra el organizador sólo a un admin). Sin
 * un caché, cada navegación entre pestañas volvería a preguntar lo mismo.
 *
 * El caché vive en el módulo y está atado al token: si alguien sale y entra con
 * otra cuenta, el token cambia y se vuelve a preguntar. Así nunca se muestra el
 * nombre ni los permisos de la sesión anterior.
 *
 * Cada vez que llega la cuenta se aplica su tema: la copia local ya pintó el
 * primer cuadro, y esto la confirma o la corrige (otra persona usó este
 * navegador, o se cambió desde otro dispositivo).
 */
interface EnMemoria {
  token: string;
  pedido: Promise<UsuarioYo>;
  usuario: UsuarioYo | null;
}

let enMemoria: EnMemoria | null = null;

/**
 * Las instancias montadas de useSesion (la barra y la página, casi siempre
 * dos). Cuando una respuesta llega, se les avisa a todas: si /yo falló sin red
 * y después la página reintentó con éxito, la barra no puede quedarse sin
 * nombre y sin la pestaña Cuentas hasta la próxima navegación.
 */
const oyentes = new Set<() => void>();

/** `mientras`: lo que se muestra hasta que llegue la respuesta. Al revalidar
 *  es la cuenta que ya se conocía, así la barra no parpadea ni se vacía. */
function pedirYo(token: string, mientras: UsuarioYo | null = null): Promise<UsuarioYo> {
  if (enMemoria?.token === token) return enMemoria.pedido;
  const pedido = admin.yo();
  const entrada: EnMemoria = { token, pedido, usuario: mientras };
  enMemoria = entrada;
  pedido.then(
    (usuario) => {
      entrada.usuario = usuario;
      if (enMemoria !== entrada) return;
      aplicarTema(usuario.tema);
      oyentes.forEach((avisar) => avisar());
    },
    () => {
      if (enMemoria !== entrada) return;
      // Si falló (sin red, Render dormido), no se guarda el fracaso: el
      // próximo que pregunte vuelve a intentar. Al revalidar, se sigue con lo
      // que se sabía: mejor eso que dejar el panel sin nombre por un corte.
      enMemoria = mientras ? { token, pedido: Promise.resolve(mientras), usuario: mientras } : null;
    },
  );
  return pedido;
}

function usuarioEnMemoria(token: string | null): UsuarioYo | null {
  return token && enMemoria?.token === token ? enMemoria.usuario : null;
}

/**
 * Para Entrar: si ya hay un token, pregunta quién es por el mismo camino que
 * useSesion, así la respuesta queda guardada. Si la sesión sirve y Entrar
 * manda a /admin, el panel ya sabe quién es y no vuelve a preguntar: un pedido
 * menos en fila, que con el servidor recién despierto son segundos. Sin token,
 * null.
 */
export function comprobarSesion(): Promise<UsuarioYo> | null {
  const token = tokenDeSesion();
  return token ? pedirYo(token) : null;
}

/**
 * Vuelve a preguntar quién es, sin cerrar la sesión. Para cuando el backend
 * contesta 403 donde el panel creía que había permiso: casi siempre, alguien le
 * cambió el rol a esta cuenta con el panel abierto. Sin esto, un admin pasado a
 * organizador seguía viendo la pestaña Cuentas, que rebotaba en cada toque.
 * Mientras llega la respuesta se sigue mostrando lo que había.
 */
export function revalidarSesion(): void {
  const token = tokenDeSesion();
  if (!token) return;
  const anterior = usuarioEnMemoria(token);
  enMemoria = null;
  pedirYo(token, anterior).catch(() => {});
}

// Cambiar la contraseña trae un token nuevo para la MISMA cuenta: lo que se
// sabía sigue valiendo, sólo cambia la llave. Sin esto, el panel entero
// volvería a "cargando" y a preguntar /yo.
alRenovarToken((anterior, nuevo) => {
  if (enMemoria && enMemoria.token === anterior) enMemoria = { ...enMemoria, token: nuevo };
});

// Esta pestaña tomó el token que guardó otra (ver client.ts): casi siempre la
// misma cuenta, que cambió la contraseña allá, pero puede ser otra que entró
// en esa pestaña. No hay forma de saberlo sin preguntar: se vuelve a pedir /yo
// y, mientras llega, se sigue mostrando lo que había, como en revalidarSesion.
// Si esta pestaña todavía no había preguntado quién es (el login, o una página
// del invitado abierta en el mismo navegador), no hay nada que corregir: la
// próxima vez que el panel pregunte, lo hará con el token nuevo.
alAdoptarToken((anterior, nuevo) => {
  const actual = enMemoria;
  if (!actual || actual.token !== anterior) return;
  enMemoria = null;
  pedirYo(nuevo, actual.usuario).catch(() => {});
});

/**
 * Para Mi cuenta: después de admin.actualizarYo, guardarAvatar o quitarAvatar,
 * pasale la cuenta que devolvió el backend. La barra, el avatar y el tema se
 * actualizan en el acto en todas las piezas montadas, sin volver a preguntar.
 *
 *   const cuenta = await admin.actualizarYo({ tema: "claro" });
 *   actualizarUsuarioEnSesion(cuenta);
 */
export function actualizarUsuarioEnSesion(usuario: UsuarioYo): void {
  const token = tokenDeSesion();
  if (!token) return;
  enMemoria = { token, pedido: Promise.resolve(usuario), usuario };
  aplicarTema(usuario.tema);
  oyentes.forEach((avisar) => avisar());
}

/** Para "Salir": olvida quién era y borra el token de esta pestaña (la copia
 *  guardada, sólo si otra pestaña no la renovó). Después, navegá al login. */
export function olvidarSesion(): void {
  enMemoria = null;
  admin.salir();
}

/**
 * Para cualquier pedido del panel que falla: si es un 401 (la sesión venció o
 * la cuenta se dio de baja con la sesión abierta), olvida la sesión, va al
 * login y devuelve true, así quien llama no muestra el error. Un 403 NO entra:
 * también viaja con NO_AUTORIZADO, pero es falta de permiso, no de sesión.
 *
 * Tampoco entra un 401 con un token que otra pestaña ya reemplazó (cambió la
 * contraseña o volvió a entrar): la sesión sigue con el token nuevo, así que
 * ni se olvida ni se va al login. Antes, ese 401 borraba del navegador justo
 * el token nuevo, y la otra pestaña caía en el login al recargar. Casi nunca
 * llega hasta acá, porque el cliente ya repite el pedido con el token nuevo;
 * si llega, devuelve false: quien llama muestra su error y reintentar anda.
 *
 *   catch (e) { if (!alPerderSesion(e)) setError(e); }
 */
export function useAlPerderSesion(): (error: unknown) => boolean {
  const navegar = useNavigate();
  return useCallback(
    (error: unknown) => {
      if (!(error instanceof ErrorApi && perdioLaSesion(error))) return false;
      olvidarSesion();
      navegar("/admin/login", { replace: true });
      return true;
    },
    [navegar],
  );
}

export interface EstadoSesion {
  /** null mientras carga, o si no se pudo saber. */
  usuario: UsuarioYo | null;
  /** admin o superadmin: ve todos los eventos y la pestaña Cuentas. */
  esAdmin: boolean;
  /** Sólo la superadmin: además gestiona a los admins. */
  esSuperadmin: boolean;
  cargando: boolean;
  /** Un error que NO es de sesión (sin red, servidor dormido). Un 401 no llega
   *  acá: manda directo al login. */
  error: unknown;
  reintentar: () => void;
}

/**
 * const { usuario, esAdmin, cargando } = useSesion();
 *
 * Sin token, o si la API responde 401 (sesión vencida, o la cuenta se dio de
 * baja mientras estaba adentro), olvida la sesión y navega a /admin/login.
 */
export function useSesion(): EstadoSesion {
  const navegar = useNavigate();
  const alPerderSesion = useAlPerderSesion();
  const token = tokenDeSesion();
  const [usuario, setUsuario] = useState<UsuarioYo | null>(() => usuarioEnMemoria(token));
  const [error, setError] = useState<unknown>(null);
  const [intento, setIntento] = useState(0);

  useEffect(() => {
    if (!token) {
      navegar("/admin/login", { replace: true });
      return;
    }
    let vivo = true;
    setError(null);
    pedirYo(token).then(
      (u) => {
        if (vivo) setUsuario(u);
      },
      (e: unknown) => {
        if (vivo && !alPerderSesion(e)) setError(e);
      },
    );
    return () => {
      vivo = false;
    };
  }, [token, navegar, alPerderSesion, intento]);

  // Si otra instancia consiguió la respuesta (por ejemplo, reintentando después
  // de un corte), ésta se entera y deja de mostrar el error.
  useEffect(() => {
    const avisar = () => {
      const enCache = usuarioEnMemoria(tokenDeSesion());
      if (!enCache) return;
      setUsuario(enCache);
      setError(null);
    };
    oyentes.add(avisar);
    return () => {
      oyentes.delete(avisar);
    };
  }, []);

  const reintentar = useCallback(() => setIntento((n) => n + 1), []);

  // Si el token cambió desde el último render, lo que hay en el estado es de
  // otra sesión: no se muestra.
  const vigente = usuario && usuarioEnMemoria(token)?.id === usuario.id ? usuario : null;

  return {
    usuario: vigente,
    esAdmin: vigente?.rol === "admin" || vigente?.rol === "superadmin",
    esSuperadmin: vigente?.rol === "superadmin",
    cargando: vigente === null && error === null,
    error,
    reintentar,
  };
}

export default useSesion;

import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import { ErrorApi, admin, tokenDeSesion } from "../api/client";
import type { UsuarioYo } from "../api/tipos";

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
      if (enMemoria === entrada) oyentes.forEach((avisar) => avisar());
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

/** Para "Salir": olvida quién era y borra el token. Después, navegá al login. */
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
 *   catch (e) { if (!alPerderSesion(e)) setError(e); }
 */
export function useAlPerderSesion(): (error: unknown) => boolean {
  const navegar = useNavigate();
  return useCallback(
    (error: unknown) => {
      if (!(error instanceof ErrorApi && error.esSinSesion)) return false;
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

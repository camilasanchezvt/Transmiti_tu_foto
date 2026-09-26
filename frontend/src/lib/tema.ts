import { useLayoutEffect, useSyncExternalStore } from "react";

import type { Tema } from "../api/tipos";

/**
 * El tema del panel: oscuro, claro o automático (el del sistema).
 *
 * Se aplica como <html data-tema="oscuro|claro">; los colores salen de las
 * variables de index.css. La preferencia es de la cuenta (GET /api/admin/yo
 * trae `tema`), pero se guarda una copia en este navegador para pintar bien
 * desde el primer cuadro: el script de index.html la lee antes de que cargue
 * React, y useSesion la confirma (o la corrige) cuando llega /yo.
 *
 * El invitado y la pantalla son SIEMPRE oscuros: se ven en un salón a oscuras
 * y en un proyector. Sus rutas van envueltas en <SiempreOscuro /> (App.tsx);
 * una página suelta puede llamar a useSiempreOscuro(). Mientras haya alguna
 * montada, el tema queda en oscuro sin tocar la preferencia guardada.
 */

export type TemaAplicado = "oscuro" | "claro";

/** La misma clave que lee el script de index.html. */
const CLAVE = "transmiti.tema";

/** El color de la barra del navegador en el celular (meta theme-color). */
const COLOR_BARRA: Record<TemaAplicado, string> = { oscuro: "#000000", claro: "#F2F2F7" };

function esTema(valor: unknown): valor is Tema {
  return valor === "oscuro" || valor === "claro" || valor === "automatico";
}

function leerCopia(): Tema {
  try {
    const guardado = window.localStorage.getItem(CLAVE);
    if (esTema(guardado)) return guardado;
  } catch {
    /* modo privado: se sigue con el del sistema */
  }
  return "automatico";
}

const consulta: MediaQueryList | null =
  typeof window !== "undefined" && typeof window.matchMedia === "function"
    ? window.matchMedia("(prefers-color-scheme: dark)")
    : null;

let preferencia: Tema = leerCopia();
/** Cuántas zonas siempre oscuras hay montadas. */
let forzados = 0;
const oyentes = new Set<() => void>();

/** Lo que se ve ahora: la preferencia resuelta, o oscuro si una zona lo fuerza.
 *  Sin forma de saber el del sistema, oscuro (el de siempre). */
export function temaAplicado(): TemaAplicado {
  if (forzados > 0) return "oscuro";
  if (preferencia === "automatico") return consulta && !consulta.matches ? "claro" : "oscuro";
  return preferencia;
}

/** La preferencia de la cuenta, o la copia local mientras no llega /yo. */
export function preferenciaTema(): Tema {
  return preferencia;
}

function pintar(): void {
  const tema = temaAplicado();
  const raiz = document.documentElement;
  if (raiz.dataset.tema !== tema) raiz.dataset.tema = tema;
  document.querySelector('meta[name="theme-color"]')?.setAttribute("content", COLOR_BARRA[tema]);
  oyentes.forEach((avisar) => avisar());
}

/**
 * Cambia la preferencia, la pinta y guarda la copia local. No habla con el
 * backend: para guardarla en la cuenta, admin.actualizarYo({ tema }) y después
 * esto (o actualizarUsuarioEnSesion, que lo llama).
 */
export function aplicarTema(nueva: Tema): void {
  if (!esTema(nueva)) return;
  preferencia = nueva;
  try {
    window.localStorage.setItem(CLAVE, nueva);
  } catch {
    /* sin copia: el próximo arranque pinta el del sistema hasta que llegue /yo */
  }
  pintar();
}

// Automático sigue al sistema también si cambia con la página abierta (el
// celular que pasa a modo oscuro al anochecer). Safari viejo sólo tiene
// addListener.
if (consulta) {
  const alCambiarSistema = () => {
    if (preferencia === "automatico") pintar();
  };
  if (typeof consulta.addEventListener === "function") consulta.addEventListener("change", alCambiarSistema);
  else consulta.addListener(alCambiarSistema);
}

// Al cargar el módulo NO se pinta: el primer cuadro ya lo resolvió el script de
// index.html, que además sabe qué rutas son siempre oscuras. Pintar acá, antes
// de que monte <SiempreOscuro />, dejaría un cuadro claro en la pantalla.

/**
 * Marca la página que lo llama como siempre oscura mientras esté montada:
 *
 *   export default function PaginaPantalla() {
 *     useSiempreOscuro();
 *     …
 *   }
 *
 * Para una ruta entera es más simple envolverla en <SiempreOscuro /> en
 * App.tsx. useLayoutEffect: cambia antes de pintar, sin un cuadro claro al
 * pasar del panel a la pantalla.
 */
export function useSiempreOscuro(): void {
  useLayoutEffect(() => {
    forzados += 1;
    pintar();
    return () => {
      forzados -= 1;
      pintar();
    };
  }, []);
}

function suscribir(avisar: () => void): () => void {
  oyentes.add(avisar);
  return () => {
    oyentes.delete(avisar);
  };
}

/** El tema que se ve ahora, y se actualiza solo. Para lo poco que no se puede
 *  pintar con clases (un <canvas>, un color que va a una librería). */
export function useTemaAplicado(): TemaAplicado {
  return useSyncExternalStore(suscribir, temaAplicado, () => "oscuro");
}

/** La preferencia actual (oscuro, claro o automático), y se actualiza sola.
 *  Para marcar la opción elegida en Mi cuenta. */
export function usePreferenciaTema(): Tema {
  return useSyncExternalStore(suscribir, preferenciaTema, () => "automatico");
}

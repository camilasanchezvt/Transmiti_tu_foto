import { useEffect } from "react";
import { useLocation } from "react-router-dom";

import type { EventoAdmin } from "../api/tipos";
import { hoyEnArgentina } from "../lib/fecha";
import { comun } from "./textos/comun";

// Cómo se va y se vuelve entre las listas (Eventos, Historial) y las páginas de
// un evento (Ajustes, Revisar fotos). Vive en un solo lugar para que las cuatro
// páginas decidan igual adónde lleva cada "‹ Volver".

type EventoConFecha = Pick<EventoAdmin, "estado" | "fecha_evento">;

/** La misma regla que el backend para `alcance=historial`, la regla de
 *  medianoche: terminado, o sin publicar con la fecha ya pasada en Argentina.
 *  Un evento abierto vive en Eventos sea cual sea su fecha: la fiesta que pasa
 *  la medianoche sigue ahí hasta que la terminen. Tiene que coincidir EXACTO
 *  con el backend: si no, "‹ Volver" y "Compartir y pantalla" llevan a una
 *  lista donde el evento no está. */
export function esDelHistorial(evento: EventoConFecha): boolean {
  return (
    evento.estado === "cerrado" || (evento.estado === "borrador" && evento.fecha_evento < hoyEnArgentina())
  );
}

/** Lo que una lista le deja en el `state` del link a un evento, para que la
 *  página del evento vuelva ahí (con el filtro que tenía) y no a otra lista. */
export interface DesdeLista {
  volverA: string;
}

export interface Lista {
  a: string;
  texto: string;
}

function volverADelState(state: unknown): string | null {
  const volverA = (state as Partial<DesdeLista> | null)?.volverA;
  // Sólo rutas del panel: el state lo puede escribir cualquier link.
  return typeof volverA === "string" && volverA.startsWith("/admin") ? volverA : null;
}

/**
 * A qué lista vuelve una página de un evento. Si se llegó desde una lista que
 * lo dejó dicho (el historial filtrado por una cuenta), a esa misma. Si no, a
 * la lista donde vive el evento; mientras el evento no cargó, a Eventos.
 *
 * Devuelve también el `state` para pasarle a los links a otra página del mismo
 * evento (de Ajustes a Revisar fotos): así el "‹ Volver" de la siguiente sigue
 * llevando a la lista de origen.
 */
export function useVolverALista(evento: EventoConFecha | null): Lista & { state: DesdeLista | null } {
  const { state } = useLocation();
  const volverA = volverADelState(state);
  if (volverA) {
    const texto = volverA.startsWith("/admin/historial") ? comun.nav.historial : comun.nav.eventos;
    return { a: volverA, texto, state: { volverA } };
  }
  if (evento && esDelHistorial(evento)) return { a: "/admin/historial", texto: comun.nav.historial, state: null };
  return { a: "/admin", texto: comun.nav.eventos, state: null };
}

/**
 * El link a la tarjeta del evento en Eventos, con "Compartir y pantalla"
 * abierto: el QR, el link y la pantalla viven ahí y no se duplican en Ajustes.
 * Sólo tiene sentido para un evento que no es del historial (Ajustes no lo
 * ofrece para los otros). Por las dudas, uno del historial va a su lista, con
 * el filtro si se venía de un historial filtrado.
 */
export function rutaACompartir(evento: EventoConFecha & { id: number }, lista: Lista): string {
  const base = !esDelHistorial(evento)
    ? "/admin"
    : lista.a.startsWith("/admin/historial")
      ? lista.a
      : "/admin/historial";
  return `${base}#${anclaDelEvento(evento.id)}`;
}

/** El id de la tarjeta de un evento en las listas: `evento-12`. */
export function anclaDelEvento(id: number): string {
  return `evento-${id}`;
}

/**
 * Si la URL trae `#evento-12`, el id 12: esa tarjeta arranca con "Compartir y
 * pantalla" abierto. Cuando la lista termina de cargar (`listo`), la trae a la
 * vista. Las tarjetas llevan `scroll-mt-24` para no quedar debajo de la barra
 * fija de arriba.
 */
export function useEventoDelAncla(listo: boolean): number | null {
  const { hash } = useLocation();
  const coincide = /^#evento-(\d+)$/.exec(hash);
  const id = coincide ? Number(coincide[1]) : null;

  useEffect(() => {
    if (!listo || id === null) return;
    document.getElementById(anclaDelEvento(id))?.scrollIntoView({ block: "start", behavior: "smooth" });
  }, [listo, id]);

  return id;
}

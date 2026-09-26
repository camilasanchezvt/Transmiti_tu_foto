// Descargas que salen directo de Cloudinary (el video del evento) y la cuenta
// de cuándo se borran las fotos y el video.
//
// El video no pasa por el backend: el link apunta a Cloudinary con la
// transformación `fl_attachment:{nombre}`, que hace que responda con
// Content-Disposition: attachment y ese nombre. Así, en iPhone y en Android
// se descarga en vez de abrirse en el reproductor, y el archivo se llama
// "casamiento-de-lu-y-fede-2026-09-01.mp4" y no "v1727…/video-3.mp4".

import { hoyEnArgentina } from "./fecha";

/** Hasta cuántos caracteres del nombre del evento entran en el archivo. */
const LARGO_MAXIMO_SLUG = 60;

/** Si del nombre no queda nada (sólo emojis, por ejemplo). Es un nombre de
 *  archivo, no un texto de la interfaz. */
const SLUG_DE_RESPALDO = "video";

/** Dónde va la transformación en una URL de video de Cloudinary:
 *  https://res.cloudinary.com/{nube}/video/upload/{acá}v123/eventos/… */
const TRAMO_VIDEO = "/video/upload/";

const FL_ATTACHMENT = "fl_attachment";

/** Desde cuántos días antes del borrado se avisa en naranja. */
export const DIAS_DE_AVISO = 7;

/**
 * slugDeEvento("Casamiento de Lú & Fede") → "casamiento-de-lu-fede"
 *
 * Minúsculas, sin acentos (la ñ queda n), espacios y separadores a guiones y
 * sólo [a-z0-9-], hasta 60 caracteres. Ni puntos ni barras: Cloudinary los
 * leería como extensión o como otra parte de la URL.
 */
export function slugDeEvento(nombre: string): string {
  return nombre
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "") // los acentos, que NFD dejó sueltos
    .toLowerCase()
    .replace(/[\s_./\\,;:&+]+/g, "-")
    .replace(/[^a-z0-9-]/g, "")
    .replace(/-+/g, "-")
    .replace(/^-|-$/g, "")
    .slice(0, LARGO_MAXIMO_SLUG)
    .replace(/-+$/, ""); // si el corte cayó justo después de un guion
}

/** "casamiento-de-lu-y-fede-2026-09-01": el nombre del archivo, sin extensión
 *  (Cloudinary le pone la suya). */
export function nombreDescargaVideo(nombreEvento: string, fecha: string): string {
  const slug = slugDeEvento(nombreEvento) || SLUG_DE_RESPALDO;
  const dia = fecha.replace(/[^0-9-]/g, "");
  return dia ? `${slug}-${dia}` : slug;
}

/**
 * La URL del video lista para descargar con un nombre legible:
 *
 *   urlDescargaVideo(".../video/upload/v123/eventos/ab12/video-1.mp4", "Cumple de Malena", "2026-09-23")
 *   → ".../video/upload/fl_attachment:cumple-de-malena-2026-09-23/v123/eventos/ab12/video-1.mp4"
 *
 * Una URL que no es de un video de Cloudinary vuelve tal cual (se abre, en vez
 * de descargarse, pero no se rompe).
 */
export function urlDescargaVideo(url: string, nombreEvento: string, fecha: string): string {
  const i = url.indexOf(TRAMO_VIDEO);
  if (i === -1) return url;
  const corte = i + TRAMO_VIDEO.length;
  const resto = url.slice(corte);
  if (resto.startsWith(FL_ATTACHMENT)) return url;
  return `${url.slice(0, corte)}${FL_ATTACHMENT}:${nombreDescargaVideo(nombreEvento, fecha)}/${resto}`;
}

/**
 * Cuántos días faltan para que se borren las fotos y el video: 0 es hoy, y
 * negativo si ya pasó la fecha y la limpieza todavía no corrió. Cuenta con el
 * "hoy" de Argentina, como el backend. Ambas son fechas "YYYY-MM-DD".
 */
export function diasParaElBorrado(fotosSeBorranEl: string, hoy: string = hoyEnArgentina()): number | null {
  const hasta = Date.parse(`${fotosSeBorranEl}T00:00:00Z`);
  const desde = Date.parse(`${hoy}T00:00:00Z`);
  if (Number.isNaN(hasta) || Number.isNaN(desde)) return null;
  return Math.round((hasta - desde) / 86_400_000);
}

/**
 * ¿Ya no se ofrece nada que dependa de los archivos del evento (revisar,
 * descargar, el video, reabrir)? Sí cuando se borraron y también desde el DÍA
 * del borrado, aunque la limpieza del backend todavía no haya pasado: ese día
 * puede borrar en cualquier momento. Es el mismo corte que el backend
 * (`limpieza.archivos_vencidos`), que desde ese día responde 410.
 */
export function sinArchivos(evento: { fotos_borradas_en: string | null; fotos_se_borran_el: string }): boolean {
  if (evento.fotos_borradas_en !== null) return true;
  const dias = diasParaElBorrado(evento.fotos_se_borran_el);
  return dias !== null && dias <= 0;
}

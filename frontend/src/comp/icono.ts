import type { ComponentType } from "react";

/**
 * Un ícono de @heroicons/react, pasado como componente (sin los <>):
 *
 *   import { ArrowDownTrayIcon } from "@heroicons/react/20/solid";
 *   <BotonChico icono={ArrowDownTrayIcon}>{textos.descargar}</BotonChico>
 *
 * Qué juego usar:
 * - @heroicons/react/24/outline: la mayoría (trazo, en reposo).
 * - @heroicons/react/24/solid: la pestaña activa y las acciones principales
 *   (Boton variante "principal").
 * - @heroicons/react/20/solid (mini): botones chicos y chips.
 *
 * Tamaños: h-5 w-5 en botones, h-6 w-6 en la barra de pestañas, h-4 w-4 en
 * chips. Siempre aria-hidden: el texto del botón ya dice qué hace. Un botón
 * sólo-ícono lleva aria-label sacado de los textos.
 *
 * Sólo pide lo que se le pasa: así entra un ícono de heroicons (un forwardRef
 * con muchas más props) y cualquier SVG propio que acepte className.
 */
export type Icono = ComponentType<{ className?: string; "aria-hidden"?: boolean | "true" | "false" }>;

/** El ícono dentro del botón grande: 20 px, pegado al texto. */
export const claseIconoBoton = "-ml-1 h-5 w-5 shrink-0";

/** El ícono dentro del botón chico: 20 px (mini), como los de Tailwind UI. */
export const claseIconoChico = "-ml-0.5 h-5 w-5 shrink-0";

/** El ícono dentro de un chip: 16 px. */
export const claseIconoChip = "h-4 w-4 shrink-0";

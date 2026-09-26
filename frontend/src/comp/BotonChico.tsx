import type { ButtonHTMLAttributes, ReactNode } from "react";

import { comun } from "../admin/textos/comun";
import { claseIconoChico, type Icono } from "./icono";

export type VarianteChica = "vidrio" | "azul" | "peligro";

const ESTILOS: Record<VarianteChica, string> = {
  vidrio: "border border-borde bg-panel text-white hover:bg-white/15",
  azul: "bg-acento text-white hover:brightness-110 active:brightness-90",
  peligro: "border border-borde bg-panel text-rojo hover:bg-white/15",
};

/**
 * Las clases del botón chico, sueltas, para darle la misma forma a un <Link> o
 * a un <a> de descarga sin envolverlos en un <button>.
 *
 *   <Link to="…" className={claseBotonChico("vidrio")}>Ajustes</Link>
 *
 * Con ícono, el link lo lleva adentro con las mismas clases del botón:
 *
 *   <a href={url} download className={claseBotonChico("vidrio")}>
 *     <ArrowDownTrayIcon aria-hidden className={claseIconoChico} />
 *     {textos.descargarVideo}
 *   </a>
 */
export function claseBotonChico(variante: VarianteChica = "vidrio"): string {
  return (
    // 44 px de alto como mínimo (min-h-11): es lo que pide Apple para que un
    // dedo acierte sin apuntar. Chico de texto, no de objetivo.
    "inline-flex min-h-11 items-center justify-center gap-1.5 rounded-full px-4 " +
    "text-center text-sm font-medium transition active:scale-[0.97] " +
    "disabled:cursor-not-allowed disabled:opacity-50 disabled:active:scale-100 " +
    `focus:outline-none focus-visible:ring-2 focus-visible:ring-acento ${ESTILOS[variante]}`
  );
}

interface Props extends ButtonHTMLAttributes<HTMLButtonElement> {
  variante?: VarianteChica;
  /** Deshabilita y muestra "Esperá…", igual que el botón grande. */
  cargando?: boolean;
  /**
   * Un ícono de heroicons a la izquierda del texto, pasado como componente:
   * icono={ClipboardDocumentIcon}, del juego mini (@heroicons/react/20/solid).
   * Es decorativo (aria-hidden): el texto sigue siendo obligatorio.
   */
  icono?: Icono;
  children: ReactNode;
}

/** Cápsula de vidrio para las acciones secundarias: Copiar, Ajustes, Cerrar… */
export default function BotonChico({
  variante = "vidrio",
  cargando = false,
  icono: IconoBoton,
  disabled,
  className = "",
  type = "button",
  children,
  ...resto
}: Props) {
  return (
    <button
      {...resto}
      // type="button" por defecto: adentro de un <form>, un botón sin type
      // envía el formulario, y un "Copiar" no debería crear un evento.
      type={type}
      disabled={disabled || cargando}
      className={`${claseBotonChico(variante)} ${className}`}
    >
      {/* Mientras carga no va el ícono: "Esperá…" no es la acción. */}
      {IconoBoton && !cargando && <IconoBoton aria-hidden className={claseIconoChico} />}
      {cargando ? comun.esperar : children}
    </button>
  );
}

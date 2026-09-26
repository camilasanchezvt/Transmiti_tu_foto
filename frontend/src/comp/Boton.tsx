import type { ButtonHTMLAttributes, ReactNode } from "react";

import { textosBase } from "./textos";

export type Variante = "principal" | "secundario" | "peligro";

interface Props extends ButtonHTMLAttributes<HTMLButtonElement> {
  variante?: Variante;
  cargando?: boolean;
  children: ReactNode;
}

const ESTILOS: Record<Variante, string> = {
  // Como los botones de iOS: el principal es una cápsula de color sólido; el
  // resto, vidrio con el texto teñido.
  principal: "bg-acento text-white hover:brightness-110 active:scale-[0.98] active:brightness-90",
  secundario: "bg-panel text-white border border-borde hover:bg-white/15 active:scale-[0.98]",
  peligro: "bg-panel text-rojo border border-borde hover:bg-white/15 active:scale-[0.98]",
};

/**
 * Las clases del botón grande, sueltas, para darle la misma forma a un <Link>
 * o a un <a> de descarga: ir a otra página o bajar un archivo es un link, no
 * un botón (se puede abrir en otra pestaña).
 *
 *   <Link to="…" className={claseBoton("principal")}>Revisar fotos</Link>
 *
 * inline-flex y no block: con w-full ocupa toda la fila igual que un botón, y
 * con un sm:w-auto encima vuelve al ancho de su texto (un flex con w-auto
 * seguiría ocupando la fila entera). Centra el texto en un link, que no lo
 * centra solo como un <button>.
 */
export function claseBoton(variante: Variante = "principal"): string {
  return (
    "inline-flex min-h-boton w-full items-center justify-center rounded-full px-6 text-center text-lg font-semibold " +
    "transition disabled:cursor-not-allowed disabled:opacity-50 " +
    `focus:outline-none focus-visible:ring-2 focus-visible:ring-acento ${ESTILOS[variante]}`
  );
}

/**
 * Mínimo 56 px de alto: se toca con una mano, en un salón oscuro y con el
 * brillo bajo. Se deshabilita solo mientras carga, que es lo que evita el
 * doble toque en subir.
 */
export default function Boton({
  variante = "principal",
  cargando = false,
  disabled,
  className = "",
  children,
  ...resto
}: Props) {
  return (
    <button {...resto} disabled={disabled || cargando} className={`${claseBoton(variante)} ${className}`}>
      {cargando ? textosBase.esperar : children}
    </button>
  );
}

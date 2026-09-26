import type { ButtonHTMLAttributes, ReactNode } from "react";

type Variante = "principal" | "secundario" | "peligro";

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
    <button
      {...resto}
      disabled={disabled || cargando}
      className={
        "min-h-boton w-full rounded-full px-6 text-lg font-semibold " +
        "transition disabled:cursor-not-allowed disabled:opacity-50 " +
        `focus:outline-none focus-visible:ring-2 focus-visible:ring-acento ${ESTILOS[variante]} ${className}`
      }
    >
      {cargando ? "Esperá…" : children}
    </button>
  );
}

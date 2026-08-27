import type { ButtonHTMLAttributes, ReactNode } from "react";

type Variante = "principal" | "secundario" | "peligro";

interface Props extends ButtonHTMLAttributes<HTMLButtonElement> {
  variante?: Variante;
  cargando?: boolean;
  children: ReactNode;
}

const ESTILOS: Record<Variante, string> = {
  principal: "bg-acento text-black hover:brightness-110 active:brightness-95",
  secundario: "bg-panel text-white border border-borde hover:border-acento",
  peligro: "bg-panel text-red-300 border border-red-900 hover:border-red-500",
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
        "min-h-boton w-full rounded-2xl px-6 text-lg font-semibold " +
        "transition disabled:cursor-not-allowed disabled:opacity-50 " +
        `focus:outline-none focus-visible:ring-2 focus-visible:ring-acento ${ESTILOS[variante]} ${className}`
      }
    >
      {cargando ? "Esperá…" : children}
    </button>
  );
}
